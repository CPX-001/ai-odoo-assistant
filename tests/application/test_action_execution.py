import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from odoo_ai.adapters import OdooGatewayError
from odoo_ai.application import (
    ACTION_POLICY_REVISION,
    ActionExecutionService,
    action_payload_fingerprint,
    canonical_action_payload_bytes,
)
from odoo_ai.contracts import (
    ActionActorContext,
    ActionCommitResult,
    ActionFieldChange,
    ActionPreview,
    ActionPreviewChange,
    ActionPreviewSummary,
    ActionProposalPayload,
    ActionProposalState,
    ActionTarget,
    ActionValue,
    ActionValueKind,
    ActionVerificationResult,
    ExecuteApprovedActionRequest,
)
from odoo_ai.ports import (
    ActionDecisionOutcome,
    StoredActionProposal,
    StoredDecisionResult,
)
from odoo_ai.security import ActionAuthorityCodec

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")
APPROVAL_ID = UUID("44444444-4444-4444-8444-444444444444")
ATTEMPT_ID = UUID("55555555-5555-4555-8555-555555555555")
EVIDENCE_ID = UUID("66666666-6666-4666-8666-666666666666")
SCHEMA_ID = "action-schema:v1:sha256:" + "a" * 64
PRECONDITION = "action-precondition:v1:sha256:" + "b" * 64


def _proposal() -> StoredActionProposal:
    payload = ActionProposalPayload(
        proposal_id=PROPOSAL_ID,
        turn_id=UUID("22222222-2222-4222-8222-222222222222"),
        instance_id="odoo-production",
        database="acme",
        uid=17,
        company_id=1,
        allowed_company_ids=(1, 3),
        target=ActionTarget(model="sale.order", record_id=42),
        changes=(
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value="PO-43"),
            ),
        ),
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
    )
    fingerprint = action_payload_fingerprint(payload)
    preview = ActionPreview(
        preview_id=UUID("33333333-3333-4333-8333-333333333333"),
        summary=ActionPreviewSummary(
            proposal_id=PROPOSAL_ID,
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
        payload_fingerprint=fingerprint,
        precondition_fingerprint=PRECONDITION,
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
    )
    return StoredActionProposal(
        payload=payload,
        canonical_payload=canonical_action_payload_bytes(payload).decode(),
        payload_fingerprint=fingerprint,
        preview=preview,
        state=ActionProposalState.APPROVED,
        created_at=NOW,
        decided_at=NOW,
        decided_by_uid=17,
        approval_id=APPROVAL_ID,
        state_version=1,
    )


def _actor() -> ActionActorContext:
    return ActionActorContext(
        instance_id="odoo-production",
        database="acme",
        uid=17,
        company_id=1,
        allowed_company_ids=(1, 3),
    )


class MemoryExecutionStore:
    def __init__(self) -> None:
        self.proposal = _proposal()
        self.transitions: list[ActionProposalState] = []

    def claim_execution(self, **values: object) -> StoredDecisionResult:
        if self.proposal.state is not ActionProposalState.APPROVED:
            return StoredDecisionResult(
                ActionDecisionOutcome.INVALID_STATE, self.proposal
            )
        actor = values["actor"]
        if actor != _actor():
            return StoredDecisionResult(ActionDecisionOutcome.BINDING_MISMATCH)
        self.proposal = replace(
            self.proposal,
            state=ActionProposalState.EXECUTING,
            attempt_id=values["attempt_id"],
            execution_started_at=values["started_at"],
        )
        return StoredDecisionResult(ActionDecisionOutcome.APPLIED, self.proposal)

    def transition_execution(self, **values: object) -> StoredActionProposal:
        assert self.proposal.state in values["expected_states"]
        assert self.proposal.attempt_id == values["attempt_id"]
        state = values["state"]
        self.transitions.append(state)
        self.proposal = replace(
            self.proposal,
            state=state,
            completed_at=values["occurred_at"],
            evidence_id=values.get("evidence_id"),
            error_code=values.get("error_code"),
            verification_payload=values.get("verification_payload"),
        )
        return self.proposal


class FakeActionGateway:
    def __init__(self, factory: "FakeGatewayFactory", token: str) -> None:
        self.factory = factory
        self.claims = factory.codec.decode(token)

    async def commit_record_patch(
        self, payload: ActionProposalPayload
    ) -> ActionCommitResult:
        self.factory.commit_calls += 1
        assert self.claims.scopes == ("action_commit",)
        if self.factory.commit_error:
            raise OdooGatewayError(self.factory.commit_error)
        return ActionCommitResult(
            proposal_id=payload.proposal_id,
            attempt_id=self.claims.attempt_id,
            committed_at=NOW + timedelta(seconds=1),
            payload_fingerprint=self.claims.payload_fingerprint,
            precondition_fingerprint=self.claims.precondition_fingerprint,
        )

    async def verify_record_patch(
        self, payload: ActionProposalPayload
    ) -> ActionVerificationResult:
        self.factory.verify_calls += 1
        assert self.claims.scopes == ("action_verify",)
        if self.factory.verify_error:
            raise OdooGatewayError(self.factory.verify_error)
        value = (
            payload.changes[0].value
            if self.factory.matches
            else ActionValue(kind=ActionValueKind.TEXT, value="PO-other")
        )
        return ActionVerificationResult(
            proposal_id=payload.proposal_id,
            attempt_id=self.claims.attempt_id,
            verified_at=NOW + timedelta(seconds=2),
            matches=self.factory.matches,
            after={"client_order_ref": value},
        )


class FakeGatewayFactory:
    def __init__(
        self,
        codec: ActionAuthorityCodec,
        *,
        commit_error: str | None = None,
        verify_error: str | None = None,
        matches: bool = True,
    ) -> None:
        self.codec = codec
        self.commit_error = commit_error
        self.verify_error = verify_error
        self.matches = matches
        self.commit_calls = 0
        self.verify_calls = 0

    def for_action(self, *, authority_token: str) -> FakeActionGateway:
        return FakeActionGateway(self, authority_token)


def _service(
    store: MemoryExecutionStore, factory: FakeGatewayFactory
) -> ActionExecutionService:
    ids = iter((ATTEMPT_ID, EVIDENCE_ID))
    return ActionExecutionService(
        store=store,
        authority_codec=factory.codec,
        gateway_factory=factory,  # type: ignore[arg-type]
        clock=lambda: NOW + timedelta(seconds=10),
        uuid_factory=lambda: next(ids, ATTEMPT_ID),
    )


def _codec() -> ActionAuthorityCodec:
    return ActionAuthorityCodec(
        b"m6-action-authority-secret-" + b"x" * 48,
        clock=lambda: int((NOW + timedelta(seconds=10)).timestamp()),
    )


def test_commit_is_one_shot_and_exact_reread_produces_verified_receipt() -> None:
    store = MemoryExecutionStore()
    factory = FakeGatewayFactory(_codec())
    service = _service(store, factory)

    receipt = asyncio.run(
        service.execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )

    assert receipt.state is ActionProposalState.VERIFIED
    assert receipt.evidence_id == EVIDENCE_ID
    assert receipt.evidence is not None
    assert receipt.evidence.kind.value == "record"
    assert receipt.evidence.status.value == "checked"
    assert factory.commit_calls == factory.verify_calls == 1
    assert store.transitions == [
        ActionProposalState.COMMITTED,
        ActionProposalState.VERIFIED,
    ]
    replay = asyncio.run(
        service.execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )
    assert replay == receipt
    assert factory.commit_calls == 1
    assert factory.verify_calls == 1


def test_stale_precondition_never_verifies_or_retries() -> None:
    store = MemoryExecutionStore()
    factory = FakeGatewayFactory(_codec(), commit_error="stale_precondition")

    receipt = asyncio.run(
        _service(store, factory).execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )

    assert receipt.state is ActionProposalState.STALE
    assert factory.commit_calls == 1
    assert factory.verify_calls == 0


def test_ambiguous_commit_is_not_retried_and_is_resolved_only_by_reread() -> None:
    store = MemoryExecutionStore()
    factory = FakeGatewayFactory(_codec(), commit_error="upstream_timeout")

    receipt = asyncio.run(
        _service(store, factory).execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )

    assert receipt.state is ActionProposalState.VERIFIED
    assert factory.commit_calls == factory.verify_calls == 1
    assert store.transitions == [
        ActionProposalState.EXECUTION_UNKNOWN,
        ActionProposalState.VERIFIED,
    ]


def test_confirmed_commit_with_mismatch_is_committed_unverified() -> None:
    store = MemoryExecutionStore()
    factory = FakeGatewayFactory(_codec(), matches=False)

    receipt = asyncio.run(
        _service(store, factory).execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )

    assert receipt.state is ActionProposalState.COMMITTED_UNVERIFIED
    assert receipt.error_code == "verification_mismatch"


def test_interrupted_executing_state_recovers_by_reread_without_commit_retry() -> None:
    store = MemoryExecutionStore()
    store.proposal = replace(
        store.proposal,
        state=ActionProposalState.EXECUTING,
        attempt_id=ATTEMPT_ID,
        execution_started_at=NOW + timedelta(seconds=5),
    )
    factory = FakeGatewayFactory(_codec())

    receipt = asyncio.run(
        _service(store, factory).execute(
            ExecuteApprovedActionRequest(approval_id=APPROVAL_ID, actor=_actor())
        )
    )

    assert receipt.state is ActionProposalState.VERIFIED
    assert factory.commit_calls == 0
    assert factory.verify_calls == 1
