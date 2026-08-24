"""PostgreSQL adapter for durable ACTION proposal decisions."""

from __future__ import annotations

import hmac
import json
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from odoo_ai.application.action_policy import (
    action_payload_fingerprint,
    canonical_action_payload_bytes,
)
from odoo_ai.contracts import (
    ActionActorContext,
    ActionCreatePreview,
    ActionDecision,
    ActionPayload,
    ActionPreview,
    ActionProposalPayload,
    ActionProposalState,
    ActionTarget,
    BusinessActionPreview,
    RecordCreateProposalPayload,
)
from odoo_ai.ports.actions import (
    ActionDecisionOutcome,
    StoredActionProposal,
    StoredDecisionResult,
)
from odoo_ai.storage.database import SessionFactory, session_scope
from odoo_ai.storage.models import ActionAuditRecord, ActionProposalRecord


class ActionStoreError(RuntimeError):
    """Fail-closed sanitized persistence error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_PAYLOAD_ADAPTER: TypeAdapter[ActionPayload] = TypeAdapter(ActionPayload)
_PREVIEW_ADAPTER: TypeAdapter[ActionPreview | ActionCreatePreview | BusinessActionPreview] = (
    TypeAdapter(ActionPreview | ActionCreatePreview | BusinessActionPreview)
)


class SqlActionApprovalStore:
    """Use PostgreSQL row locks to serialize decisions for one proposal."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_preview(self, proposal: StoredActionProposal) -> None:
        if proposal.state is not ActionProposalState.PREVIEWED:
            raise ActionStoreError("invalid_state")
        payload = proposal.payload
        preview = proposal.preview
        record = ActionProposalRecord(
            proposal_id=payload.proposal_id,
            format_version=payload.format_version,
            action_kind=payload.action_kind.value,
            turn_id=payload.turn_id,
            workflow="ACTION",
            instance_id=payload.instance_id,
            database=payload.database,
            uid=payload.uid,
            company_id=payload.company_id,
            allowed_company_ids=list(payload.allowed_company_ids),
            target_model=payload.target.model,
            target_record_id=_target_record_id(payload),
            canonical_payload=proposal.canonical_payload,
            payload_fingerprint=proposal.payload_fingerprint,
            policy_revision=payload.policy_revision,
            schema_revision=(
                payload.schema_revision
                if isinstance(payload, (ActionProposalPayload, RecordCreateProposalPayload))
                else payload.action_spec_revision
            ),
            preview_id=preview.preview_id,
            preview_payload=cast(dict[str, JsonValue], preview.model_dump(mode="json")),
            precondition_fingerprint=preview.precondition_fingerprint,
            previewed_at=preview.observed_at,
            expires_at=preview.expires_at,
            state=proposal.state.value,
            state_version=proposal.state_version,
            created_at=proposal.created_at,
            updated_at=proposal.created_at,
        )
        try:
            with session_scope(self._session_factory) as session:
                session.add(record)
                session.flush()
                _audit(session, record, "previewed", proposal.created_at)
        except IntegrityError:
            raise ActionStoreError("proposal_conflict") from None

    def get_by_proposal_id(self, proposal_id: UUID) -> StoredActionProposal | None:
        with self._session_factory() as session:
            record = session.get(ActionProposalRecord, proposal_id)
            return None if record is None else _snapshot(record)

    def get_by_approval_id(self, approval_id: UUID) -> StoredActionProposal | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(ActionProposalRecord).where(ActionProposalRecord.approval_id == approval_id)
            )
            return None if record is None else _snapshot(record)

    def decide(
        self,
        *,
        proposal_id: UUID,
        decision: ActionDecision,
        actor: ActionActorContext,
        decided_at: datetime,
        approval_id: UUID | None,
    ) -> StoredDecisionResult:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(ActionProposalRecord)
                .where(ActionProposalRecord.proposal_id == proposal_id)
                .with_for_update()
            )
            if record is None:
                return StoredDecisionResult(ActionDecisionOutcome.NOT_FOUND)
            try:
                current = _snapshot(record)
            except ActionStoreError:
                return StoredDecisionResult(ActionDecisionOutcome.CORRUPT)
            if not _actor_matches(current.payload, actor):
                return StoredDecisionResult(ActionDecisionOutcome.BINDING_MISMATCH)
            if current.state is not ActionProposalState.PREVIEWED:
                return StoredDecisionResult(ActionDecisionOutcome.INVALID_STATE, current)
            if decided_at >= current.preview.expires_at:
                record.state = ActionProposalState.EXPIRED.value
                record.state_version += 1
                record.updated_at = decided_at
                session.flush()
                _audit(session, record, "expired", decided_at)
                return StoredDecisionResult(ActionDecisionOutcome.EXPIRED, _snapshot(record))

            if decision is ActionDecision.APPROVE:
                if approval_id is None:
                    raise ActionStoreError("invalid_approval_handle")
                record.state = ActionProposalState.APPROVED.value
                record.decision = ActionDecision.APPROVE.value
                record.approval_id = approval_id
            else:
                if approval_id is not None:
                    raise ActionStoreError("invalid_approval_handle")
                record.state = ActionProposalState.REJECTED.value
                record.decision = ActionDecision.REJECT.value
            record.decided_by_uid = actor.uid
            record.decided_at = decided_at
            record.state_version += 1
            record.updated_at = decided_at
            session.flush()
            _audit(session, record, "approved" if approval_id else "rejected", decided_at)
            return StoredDecisionResult(ActionDecisionOutcome.APPLIED, _snapshot(record))

    def claim_execution(
        self,
        *,
        approval_id: UUID,
        actor: ActionActorContext,
        attempt_id: UUID,
        started_at: datetime,
    ) -> StoredDecisionResult:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(ActionProposalRecord)
                .where(ActionProposalRecord.approval_id == approval_id)
                .with_for_update()
            )
            if record is None:
                return StoredDecisionResult(ActionDecisionOutcome.NOT_FOUND)
            current = _snapshot(record)
            if not _actor_matches(current.payload, actor):
                return StoredDecisionResult(ActionDecisionOutcome.BINDING_MISMATCH)
            if current.state is not ActionProposalState.APPROVED:
                return StoredDecisionResult(ActionDecisionOutcome.INVALID_STATE, current)
            if started_at >= current.preview.expires_at:
                record.state = ActionProposalState.EXPIRED.value
                record.state_version += 1
                record.updated_at = started_at
                _audit(session, record, "expired", started_at)
                return StoredDecisionResult(ActionDecisionOutcome.EXPIRED, _snapshot(record))
            record.state = ActionProposalState.EXECUTING.value
            record.attempt_id = attempt_id
            record.execution_started_at = started_at
            record.state_version += 1
            record.updated_at = started_at
            session.flush()
            _audit(session, record, "execution_claimed", started_at)
            return StoredDecisionResult(ActionDecisionOutcome.APPLIED, _snapshot(record))

    def transition_execution(
        self,
        *,
        proposal_id: UUID,
        attempt_id: UUID,
        expected_states: tuple[ActionProposalState, ...],
        state: ActionProposalState,
        occurred_at: datetime,
        evidence_id: UUID | None = None,
        error_code: str | None = None,
        verification_payload: dict[str, object] | None = None,
    ) -> StoredActionProposal:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(ActionProposalRecord)
                .where(ActionProposalRecord.proposal_id == proposal_id)
                .with_for_update()
            )
            if (
                record is None
                or record.attempt_id != attempt_id
                or ActionProposalState(record.state) not in expected_states
            ):
                raise ActionStoreError("invalid_execution_state")
            record.state = state.value
            record.completed_at = occurred_at
            record.evidence_id = evidence_id
            record.error_code = error_code
            record.verification_payload = cast(dict[str, JsonValue] | None, verification_payload)
            record.state_version += 1
            record.updated_at = occurred_at
            session.flush()
            _audit(session, record, state.value, occurred_at)
            return _snapshot(record)


def _snapshot(record: ActionProposalRecord) -> StoredActionProposal:
    try:
        payload = _PAYLOAD_ADAPTER.validate_json(record.canonical_payload)
        preview = _PREVIEW_ADAPTER.validate_json(json.dumps(record.preview_payload))
        state = ActionProposalState(record.state)
    except (ValidationError, ValueError, TypeError):
        raise ActionStoreError("corrupt_proposal") from None
    canonical = canonical_action_payload_bytes(payload).decode("utf-8")
    expected_fingerprint = action_payload_fingerprint(payload)
    if (
        not _constant_time_text_equal(canonical, record.canonical_payload)
        or not hmac.compare_digest(expected_fingerprint, record.payload_fingerprint)
        or record.proposal_id != payload.proposal_id
        or record.action_kind != payload.action_kind.value
        or record.turn_id != payload.turn_id
        or record.instance_id != payload.instance_id
        or record.database != payload.database
        or record.uid != payload.uid
        or record.company_id != payload.company_id
        or tuple(record.allowed_company_ids) != payload.allowed_company_ids
        or record.target_model != payload.target.model
        or record.target_record_id != _target_record_id(payload)
        or record.policy_revision != payload.policy_revision
        or record.schema_revision
        != (
            payload.schema_revision
            if isinstance(payload, (ActionProposalPayload, RecordCreateProposalPayload))
            else payload.action_spec_revision
        )
        or record.preview_id != preview.preview_id
        or preview.summary.proposal_id != payload.proposal_id
        or preview.summary.target != payload.target
        or not hmac.compare_digest(preview.payload_fingerprint, expected_fingerprint)
        or not hmac.compare_digest(
            record.precondition_fingerprint, preview.precondition_fingerprint
        )
        or record.previewed_at != preview.observed_at
        or record.expires_at != preview.expires_at
        or record.state_version < 0
        or not _execution_shape_is_valid(record, state)
    ):
        raise ActionStoreError("corrupt_proposal")
    return StoredActionProposal(
        payload=payload,
        canonical_payload=canonical,
        payload_fingerprint=expected_fingerprint,
        preview=preview,
        state=state,
        created_at=record.created_at,
        decided_at=record.decided_at,
        decided_by_uid=record.decided_by_uid,
        approval_id=record.approval_id,
        state_version=record.state_version,
        attempt_id=record.attempt_id,
        execution_started_at=record.execution_started_at,
        completed_at=record.completed_at,
        evidence_id=record.evidence_id,
        error_code=record.error_code,
        verification_payload=cast(dict[str, object] | None, record.verification_payload),
    )


def _target_record_id(payload: ActionPayload) -> int | None:
    return payload.target.record_id if isinstance(payload.target, ActionTarget) else None


def _constant_time_text_equal(left: str, right: str) -> bool:
    """Compare canonical JSON safely even when business values contain Unicode."""

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _execution_shape_is_valid(record: ActionProposalRecord, state: ActionProposalState) -> bool:
    if state in {
        ActionProposalState.PREVIEWED,
        ActionProposalState.APPROVED,
        ActionProposalState.REJECTED,
        ActionProposalState.EXPIRED,
    }:
        return (
            record.attempt_id is None
            and record.execution_started_at is None
            and record.completed_at is None
        )
    if state is ActionProposalState.EXECUTING:
        return (
            record.attempt_id is not None
            and record.execution_started_at is not None
            and record.completed_at is None
        )
    return (
        record.attempt_id is not None
        and record.execution_started_at is not None
        and record.completed_at is not None
    )


def _audit(session: Session, record: ActionProposalRecord, event_type: str, at: datetime) -> None:
    session.add(
        ActionAuditRecord(
            proposal_id=record.proposal_id,
            attempt_id=record.attempt_id,
            event_type=event_type,
            state=record.state,
            actor_uid=record.uid,
            payload_fingerprint=record.payload_fingerprint,
            error_code=record.error_code,
            attributes={
                "action_kind": record.action_kind,
                "action_id": (
                    record.preview_payload.get("action_id")
                    if record.action_kind == "business_action"
                    else None
                ),
                "policy_revision": record.policy_revision,
                "schema_revision": record.schema_revision,
                "target_model": record.target_model,
                "target_record_id": record.target_record_id,
            },
            created_at=at,
        )
    )


def _actor_matches(payload: ActionPayload, actor: ActionActorContext) -> bool:
    return (
        actor.instance_id == payload.instance_id
        and actor.database == payload.database
        and actor.uid == payload.uid
        and actor.company_id == payload.company_id
        and actor.allowed_company_ids == payload.allowed_company_ids
    )
