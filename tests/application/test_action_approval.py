import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.application import ActionApprovalError, ActionApprovalService
from odoo_ai.application.action_policy import (
    ACTION_POLICY_REVISION,
    action_payload_fingerprint,
    canonical_action_payload_bytes,
)
from odoo_ai.contracts import (
    ActionActorContext,
    ActionDecision,
    ActionDecisionRequest,
    ActionFieldChange,
    ActionPreview,
    ActionPreviewChange,
    ActionPreviewSummary,
    ActionProposalPayload,
    ActionProposalState,
    ActionTarget,
    ActionValue,
    ActionValueKind,
    PersistActionPreviewRequest,
)
from odoo_ai.ports import (
    ActionDecisionOutcome,
    StoredActionProposal,
    StoredDecisionResult,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")
TURN_ID = UUID("22222222-2222-4222-8222-222222222222")
PREVIEW_ID = UUID("33333333-3333-4333-8333-333333333333")
APPROVAL_ID = UUID("44444444-4444-4444-8444-444444444444")
SCHEMA_ID = "action-schema:v1:sha256:" + "a" * 64
PRECONDITION = "action-precondition:v1:sha256:" + "b" * 64


class InMemoryActionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.proposals: dict[UUID, StoredActionProposal] = {}

    def create_preview(self, proposal: StoredActionProposal) -> None:
        with self._lock:
            if proposal.payload.proposal_id in self.proposals:
                error = RuntimeError("proposal_conflict")
                error.code = "proposal_conflict"  # type: ignore[attr-defined]
                raise error
            self.proposals[proposal.payload.proposal_id] = proposal

    def get_by_proposal_id(self, proposal_id: UUID) -> StoredActionProposal | None:
        return self.proposals.get(proposal_id)

    def get_by_approval_id(self, approval_id: UUID) -> StoredActionProposal | None:
        return next(
            (
                proposal
                for proposal in self.proposals.values()
                if proposal.approval_id == approval_id
            ),
            None,
        )

    def decide(
        self,
        *,
        proposal_id: UUID,
        decision: ActionDecision,
        actor: ActionActorContext,
        decided_at: datetime,
        approval_id: UUID | None,
    ) -> StoredDecisionResult:
        with self._lock:
            current = self.proposals.get(proposal_id)
            if current is None:
                return StoredDecisionResult(ActionDecisionOutcome.NOT_FOUND)
            payload = current.payload
            if (
                actor.instance_id != payload.instance_id
                or actor.database != payload.database
                or actor.uid != payload.uid
                or actor.company_id != payload.company_id
                or actor.allowed_company_ids != payload.allowed_company_ids
            ):
                return StoredDecisionResult(ActionDecisionOutcome.BINDING_MISMATCH)
            if current.state is not ActionProposalState.PREVIEWED:
                return StoredDecisionResult(
                    ActionDecisionOutcome.INVALID_STATE, current
                )
            if decided_at >= current.preview.expires_at:
                expired = replace(
                    current,
                    state=ActionProposalState.EXPIRED,
                    state_version=current.state_version + 1,
                )
                self.proposals[proposal_id] = expired
                return StoredDecisionResult(ActionDecisionOutcome.EXPIRED, expired)
            state = (
                ActionProposalState.APPROVED
                if decision is ActionDecision.APPROVE
                else ActionProposalState.REJECTED
            )
            decided = replace(
                current,
                state=state,
                decided_at=decided_at,
                decided_by_uid=actor.uid,
                approval_id=approval_id,
                state_version=current.state_version + 1,
            )
            self.proposals[proposal_id] = decided
            return StoredDecisionResult(ActionDecisionOutcome.APPLIED, decided)


def _payload(**updates: object) -> ActionProposalPayload:
    values: dict[str, object] = {
        "proposal_id": PROPOSAL_ID,
        "turn_id": TURN_ID,
        "instance_id": "odoo-production",
        "database": "acme",
        "uid": 17,
        "company_id": 1,
        "allowed_company_ids": (1, 3),
        "target": ActionTarget(model="sale.order", record_id=42),
        "changes": (
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value="PO-43"),
            ),
        ),
        "policy_revision": ACTION_POLICY_REVISION,
        "schema_revision": SCHEMA_ID,
    }
    values.update(updates)
    return ActionProposalPayload.model_validate(values)


def _preview(
    payload: ActionProposalPayload, *, expires_at: datetime | None = None
) -> ActionPreview:
    return ActionPreview(
        preview_id=PREVIEW_ID,
        summary=ActionPreviewSummary(
            proposal_id=payload.proposal_id,
            target=payload.target,
            changes=(
                ActionPreviewChange(
                    field="client_order_ref",
                    label="Customer Reference",
                    before=ActionValue(kind=ActionValueKind.TEXT, value="PO-42"),
                    after=payload.changes[0].value,
                ),
            ),
            warnings=("Preview only.",),
        ),
        payload_fingerprint=action_payload_fingerprint(payload),
        precondition_fingerprint=PRECONDITION,
        policy_revision=payload.policy_revision,
        schema_revision=payload.schema_revision,
        observed_at=NOW,
        expires_at=expires_at or NOW + timedelta(minutes=2),
    )


def _actor(**updates: object) -> ActionActorContext:
    values: dict[str, object] = {
        "instance_id": "odoo-production",
        "database": "acme",
        "uid": 17,
        "company_id": 1,
        "allowed_company_ids": (1, 3),
    }
    values.update(updates)
    return ActionActorContext.model_validate(values)


def _service(
    store: InMemoryActionStore, *, now: datetime = NOW + timedelta(seconds=10)
) -> ActionApprovalService:
    return ActionApprovalService(
        store,
        clock=lambda: now,
        approval_id_factory=lambda: APPROVAL_ID,
    )


def _persist(store: InMemoryActionStore) -> PersistActionPreviewRequest:
    payload = _payload()
    request = PersistActionPreviewRequest(payload=payload, preview=_preview(payload))
    _service(store).persist_preview(request)
    return request


def test_preview_round_trip_preserves_exact_canonical_payload_and_fingerprint() -> None:
    store = InMemoryActionStore()
    request = _persist(store)

    stored = store.get_by_proposal_id(PROPOSAL_ID)
    assert stored is not None
    assert stored.canonical_payload.encode() == canonical_action_payload_bytes(
        request.payload
    )
    assert stored.payload_fingerprint == action_payload_fingerprint(request.payload)
    assert stored.preview == request.preview
    assert stored.state is ActionProposalState.PREVIEWED


def test_matching_actor_can_approve_and_receives_one_opaque_handle() -> None:
    store = InMemoryActionStore()
    _persist(store)

    receipt = _service(store).decide(
        ActionDecisionRequest(
            proposal_id=PROPOSAL_ID,
            decision=ActionDecision.APPROVE,
            actor=_actor(),
        )
    )

    assert receipt.approval_id == APPROVAL_ID
    assert receipt.state is ActionProposalState.APPROVED
    assert receipt.payload_fingerprint == action_payload_fingerprint(_payload())
    approved = _service(store).load_approved(approval_id=APPROVAL_ID, actor=_actor())
    assert (
        approved.canonical_payload
        == canonical_action_payload_bytes(_payload()).decode()
    )


@pytest.mark.parametrize(
    "actor",
    [
        _actor(instance_id="other"),
        _actor(database="other"),
        _actor(uid=18),
        _actor(company_id=3),
        _actor(allowed_company_ids=(1,)),
    ],
)
def test_actor_or_context_mismatch_fails_closed(actor: ActionActorContext) -> None:
    store = InMemoryActionStore()
    _persist(store)

    with pytest.raises(ActionApprovalError, match="approval_binding_mismatch"):
        _service(store).decide(
            ActionDecisionRequest(
                proposal_id=PROPOSAL_ID,
                decision=ActionDecision.APPROVE,
                actor=actor,
            )
        )

    assert store.proposals[PROPOSAL_ID].state is ActionProposalState.PREVIEWED


def test_expired_and_rejected_proposals_cannot_be_approved() -> None:
    expired_store = InMemoryActionStore()
    _persist(expired_store)
    with pytest.raises(ActionApprovalError, match="approval_expired"):
        _service(expired_store, now=NOW + timedelta(minutes=3)).decide(
            ActionDecisionRequest(
                proposal_id=PROPOSAL_ID,
                decision=ActionDecision.APPROVE,
                actor=_actor(),
            )
        )
    assert expired_store.proposals[PROPOSAL_ID].state is ActionProposalState.EXPIRED

    rejected_store = InMemoryActionStore()
    _persist(rejected_store)
    _service(rejected_store).decide(
        ActionDecisionRequest(
            proposal_id=PROPOSAL_ID,
            decision=ActionDecision.REJECT,
            actor=_actor(),
        )
    )
    with pytest.raises(ActionApprovalError, match="proposal_already_decided"):
        _service(rejected_store).decide(
            ActionDecisionRequest(
                proposal_id=PROPOSAL_ID,
                decision=ActionDecision.APPROVE,
                actor=_actor(),
            )
        )


def test_concurrent_duplicate_approval_has_exactly_one_transition() -> None:
    store = InMemoryActionStore()
    _persist(store)
    request = ActionDecisionRequest(
        proposal_id=PROPOSAL_ID,
        decision=ActionDecision.APPROVE,
        actor=_actor(),
    )

    def approve() -> str:
        try:
            _service(store).decide(request)
        except ActionApprovalError as error:
            return error.code
        return "approved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))

    assert sorted(results) == ["approved", "proposal_already_decided"]
    assert store.proposals[PROPOSAL_ID].state_version == 1


def test_payload_preview_tampering_and_browser_replacements_are_rejected() -> None:
    payload = _payload()
    preview = _preview(payload).model_copy(
        update={"payload_fingerprint": "action-payload:v1:sha256:" + "0" * 64}
    )
    with pytest.raises(ActionApprovalError, match="preview_binding_mismatch"):
        _service(InMemoryActionStore()).persist_preview(
            PersistActionPreviewRequest(payload=payload, preview=preview)
        )

    raw = {
        "proposal_id": str(PROPOSAL_ID),
        "decision": "approve",
        "actor": _actor().model_dump(mode="json"),
        "values": {"client_order_ref": "attacker replacement"},
    }
    with pytest.raises(ValidationError):
        ActionDecisionRequest.model_validate(raw)


def test_persisted_shape_contains_no_token_secret_prompt_or_delegation() -> None:
    store = InMemoryActionStore()
    _persist(store)
    stored = store.proposals[PROPOSAL_ID]
    serialized = json.dumps(
        {
            "payload": stored.canonical_payload,
            "preview": stored.preview.model_dump(mode="json"),
        },
        sort_keys=True,
    ).casefold()

    assert "delegation_token" not in serialized
    assert "shared_secret" not in serialized
    assert "system_prompt" not in serialized
    assert "approval_token" not in serialized
