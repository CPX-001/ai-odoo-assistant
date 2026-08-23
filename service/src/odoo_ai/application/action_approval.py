"""Durable payload-bound ACTION approval state machine."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from odoo_ai.application.action_policy import (
    ActionPolicy,
    ActionPolicyError,
    action_payload_fingerprint,
    canonical_action_payload_bytes,
)
from odoo_ai.contracts import (
    ActionActorContext,
    ActionDecision,
    ActionDecisionReceipt,
    ActionDecisionRequest,
    ActionProposalState,
    PersistActionPreviewRequest,
    PersistActionPreviewResponse,
)
from odoo_ai.ports.actions import (
    ActionApprovalStore,
    ActionDecisionOutcome,
    StoredActionProposal,
)


class ActionApprovalError(RuntimeError):
    """Sanitized state-machine rejection."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ActionApprovalService:
    """Persist previews and serialize one authenticated user decision."""

    def __init__(
        self,
        store: ActionApprovalStore,
        *,
        policy: ActionPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
        approval_id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._store = store
        self._policy = policy or ActionPolicy()
        self._clock = clock or _utc_now
        self._approval_id_factory = approval_id_factory or uuid4

    def persist_preview(self, request: PersistActionPreviewRequest) -> PersistActionPreviewResponse:
        payload = request.payload
        preview = request.preview
        try:
            self._policy.validate_payload(payload)
        except ActionPolicyError as error:
            raise ActionApprovalError(error.code, 422) from None
        fingerprint = action_payload_fingerprint(payload)
        _validate_preview_binding(request, fingerprint)
        now = _aware_now(self._clock)
        if now >= preview.expires_at:
            raise ActionApprovalError("preview_expired", 410)
        canonical_payload = canonical_action_payload_bytes(payload).decode("utf-8")
        stored = StoredActionProposal(
            payload=payload,
            canonical_payload=canonical_payload,
            payload_fingerprint=fingerprint,
            preview=preview,
            state=ActionProposalState.PREVIEWED,
            created_at=now,
        )
        try:
            self._store.create_preview(stored)
        except Exception as error:  # noqa: BLE001 - sanitize storage adapter failures
            code = getattr(error, "code", None)
            if code == "proposal_conflict":
                raise ActionApprovalError("proposal_conflict") from None
            raise ActionApprovalError("approval_store_unavailable", 503) from None
        return PersistActionPreviewResponse(
            proposal_id=payload.proposal_id,
            payload_fingerprint=fingerprint,
            precondition_fingerprint=preview.precondition_fingerprint,
            expires_at=preview.expires_at,
        )

    def decide(self, request: ActionDecisionRequest) -> ActionDecisionReceipt:
        now = _aware_now(self._clock)
        approval_id = (
            self._approval_id_factory() if request.decision is ActionDecision.APPROVE else None
        )
        if approval_id is not None and not isinstance(approval_id, UUID):
            raise ActionApprovalError("approval_id_unavailable", 503)
        try:
            result = self._store.decide(
                proposal_id=request.proposal_id,
                decision=request.decision,
                actor=request.actor,
                decided_at=now,
                approval_id=approval_id,
            )
        except Exception:  # noqa: BLE001 - sanitize storage adapter failures
            raise ActionApprovalError("approval_store_unavailable", 503) from None
        if result.outcome is not ActionDecisionOutcome.APPLIED:
            _raise_decision_outcome(result.outcome)
        proposal = result.proposal
        if proposal is None or proposal.decided_at is None:
            raise ActionApprovalError("approval_store_corrupt", 503)
        expected_state = (
            ActionProposalState.APPROVED
            if request.decision is ActionDecision.APPROVE
            else ActionProposalState.REJECTED
        )
        if (
            proposal.state is not expected_state
            or proposal.decided_by_uid != request.actor.uid
            or proposal.approval_id != approval_id
        ):
            raise ActionApprovalError("approval_store_corrupt", 503)
        return ActionDecisionReceipt(
            proposal_id=proposal.payload.proposal_id,
            approval_id=proposal.approval_id,
            state=cast(
                Literal[
                    ActionProposalState.APPROVED,
                    ActionProposalState.REJECTED,
                ],
                proposal.state,
            ),
            payload_fingerprint=proposal.payload_fingerprint,
            decided_by_uid=proposal.decided_by_uid,
            decided_at=proposal.decided_at,
            expires_at=proposal.preview.expires_at,
        )

    def load_approved(
        self, *, approval_id: UUID, actor: ActionActorContext
    ) -> StoredActionProposal:
        """Return immutable approved data for M6-05 without consuming it."""

        try:
            proposal = self._store.get_by_approval_id(approval_id)
        except Exception:  # noqa: BLE001
            raise ActionApprovalError("approval_store_unavailable", 503) from None
        if proposal is None:
            raise ActionApprovalError("approval_not_found", 404)
        if not _actor_matches(proposal, actor):
            raise ActionApprovalError("approval_binding_mismatch", 403)
        now = _aware_now(self._clock)
        if now >= proposal.preview.expires_at:
            raise ActionApprovalError("approval_expired", 410)
        if proposal.state is not ActionProposalState.APPROVED:
            raise ActionApprovalError("approval_not_executable")
        return proposal


def _validate_preview_binding(request: PersistActionPreviewRequest, fingerprint: str) -> None:
    payload = request.payload
    preview = request.preview
    expected_after = {change.field: change.value for change in payload.changes}
    actual_after = {change.field: change.after for change in preview.summary.changes}
    if (
        preview.summary.proposal_id != payload.proposal_id
        or preview.summary.target != payload.target
        or not hmac.compare_digest(preview.payload_fingerprint, fingerprint)
        or preview.policy_revision != payload.policy_revision
        or preview.schema_revision != payload.schema_revision
        or len(actual_after) != len(preview.summary.changes)
        or actual_after != expected_after
    ):
        raise ActionApprovalError("preview_binding_mismatch", 422)


def _raise_decision_outcome(outcome: ActionDecisionOutcome) -> None:
    if outcome is ActionDecisionOutcome.NOT_FOUND:
        raise ActionApprovalError("proposal_not_found", 404)
    if outcome is ActionDecisionOutcome.BINDING_MISMATCH:
        raise ActionApprovalError("approval_binding_mismatch", 403)
    if outcome is ActionDecisionOutcome.EXPIRED:
        raise ActionApprovalError("approval_expired", 410)
    if outcome is ActionDecisionOutcome.INVALID_STATE:
        raise ActionApprovalError("proposal_already_decided")
    raise ActionApprovalError("approval_store_corrupt", 503)


def _actor_matches(proposal: StoredActionProposal, actor: ActionActorContext) -> bool:
    payload = proposal.payload
    return (
        actor.instance_id == payload.instance_id
        and actor.database == payload.database
        and actor.uid == payload.uid
        and actor.company_id == payload.company_id
        and actor.allowed_company_ids == payload.allowed_company_ids
    )


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ActionApprovalError("clock_unavailable", 503)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
