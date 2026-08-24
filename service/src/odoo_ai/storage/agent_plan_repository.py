"""PostgreSQL adapter for immutable unified-agent plans."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import JsonValue, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from odoo_ai.application.agent_plans import (
    RECOVERABLE_EXECUTION_ERROR,
    _plan_fingerprint,
)
from odoo_ai.application.agent_policy import POLICY_REVISION, agent_policy_fingerprint
from odoo_ai.contracts import (
    AgentPlanMetadata,
    AgentPlanStep,
    AuthorizationSource,
    EffectiveAgentPolicy,
    EffectScope,
    PlanState,
    RiskLevel,
)
from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.ports.agent_plans import (
    AgentPlanTransitionOutcome,
    AgentPlanTransitionResult,
    StoredAgentPlan,
    StoredAgentPlanStepResult,
)
from odoo_ai.storage.agent_models import (
    AgentPlanAuditRecord,
    AgentPlanRecord,
    AgentPlanStepRecord,
)
from odoo_ai.storage.database import SessionFactory, session_scope


class AgentPlanStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SqlAgentPlanStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, plan: StoredAgentPlan) -> None:
        record = AgentPlanRecord(
            plan_id=plan.plan_id,
            turn_id=plan.turn_id,
            conversation_id=plan.conversation_id,
            database=plan.actor.database,
            uid=plan.actor.uid,
            company_id=plan.company_id,
            allowed_company_ids=list(plan.allowed_company_ids),
            goal=plan.goal,
            answer_markdown=plan.answer_markdown,
            confidence=plan.confidence.value,
            assumptions=list(plan.assumptions),
            state=plan.state.value,
            risk=plan.risk.value,
            metadata_payload=cast(
                dict[str, JsonValue], plan.metadata.model_dump(mode="json")
            ),
            policy_snapshot=cast(
                dict[str, JsonValue], plan.policy.model_dump(mode="json")
            ),
            policy_fingerprint=plan.policy.fingerprint,
            canonical_plan=cast(dict[str, JsonValue], plan.canonical_plan),
            plan_fingerprint=plan.plan_fingerprint,
            requires_confirmation=plan.requires_confirmation,
            authorization_id=plan.authorization_id,
            authorization_source=(
                plan.authorization_source.value if plan.authorization_source else None
            ),
            decided_by_uid=plan.decided_by_uid,
            decided_at=plan.decided_at,
            execution_started_at=plan.execution_started_at,
            completed_at=plan.completed_at,
            expires_at=plan.expires_at,
            error_code=plan.error_code,
            state_version=plan.state_version,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
        steps = [
            AgentPlanStepRecord(
                plan_id=plan.plan_id,
                position=position,
                step_id=step.step_id,
                title=step.title,
                tool_name=step.tool_name,
                arguments=step.arguments,
                dependencies=list(step.depends_on),
                risk=step.risk.value,
                effect_scope=step.effect_scope.value,
                is_write=step.is_write,
                is_business_action=step.is_business_action,
                atomic=step.atomic,
                estimated_records=step.estimated_records,
                payload_fingerprint=step.payload_fingerprint,
                proposal_id=step.proposal_id,
                proposal_fingerprint=step.proposal_fingerprint,
                state="planned",
                created_at=plan.created_at,
                updated_at=plan.created_at,
            )
            for position, step in enumerate(plan.steps)
        ]
        try:
            with session_scope(self._session_factory) as session:
                session.add(record)
                session.add_all(steps)
                session.flush()
                _audit(session, record, "created", plan.created_at)
                if plan.authorization_source is AuthorizationSource.EFFECTIVE_POLICY:
                    _audit(session, record, "authorized_by_policy", plan.created_at)
        except IntegrityError:
            raise AgentPlanStoreError("agent_plan_conflict") from None

    def get(self, plan_id: UUID) -> StoredAgentPlan | None:
        with self._session_factory() as session:
            record = session.get(AgentPlanRecord, plan_id)
            if record is None:
                return None
            return _snapshot(session, record)

    def decide(
        self,
        *,
        plan_id: UUID,
        actor: ChatActor,
        approve: bool,
        authorization_id: UUID | None,
        decided_at: datetime,
    ) -> AgentPlanTransitionResult:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AgentPlanRecord)
                .where(AgentPlanRecord.plan_id == plan_id)
                .with_for_update()
            )
            if record is None:
                return AgentPlanTransitionResult(AgentPlanTransitionOutcome.NOT_FOUND)
            if record.database != actor.database or record.uid != actor.uid:
                return AgentPlanTransitionResult(
                    AgentPlanTransitionOutcome.BINDING_MISMATCH
                )
            if record.state != PlanState.AWAITING_CONFIRMATION.value:
                return AgentPlanTransitionResult(AgentPlanTransitionOutcome.INVALID_STATE)
            if decided_at >= record.expires_at:
                record.state = PlanState.EXPIRED.value
                record.state_version += 1
                record.updated_at = decided_at
                _audit(session, record, "expired", decided_at)
                return AgentPlanTransitionResult(
                    AgentPlanTransitionOutcome.EXPIRED,
                    _snapshot(session, record),
                )
            if approve:
                if authorization_id is None:
                    raise AgentPlanStoreError("agent_authorization_missing")
                record.state = PlanState.AUTHORIZED.value
                record.authorization_id = authorization_id
                record.authorization_source = AuthorizationSource.USER_CONFIRMATION.value
                event_type = "authorized_by_user"
            else:
                if authorization_id is not None:
                    raise AgentPlanStoreError("agent_authorization_invalid")
                record.state = PlanState.REJECTED.value
                record.completed_at = decided_at
                event_type = "rejected"
            record.decided_by_uid = actor.uid
            record.decided_at = decided_at
            record.state_version += 1
            record.updated_at = decided_at
            session.flush()
            _audit(session, record, event_type, decided_at)
            return AgentPlanTransitionResult(
                AgentPlanTransitionOutcome.APPLIED,
                _snapshot(session, record),
            )

    def claim_execution(
        self,
        *,
        plan_id: UUID,
        actor: ChatActor,
        started_at: datetime,
    ) -> AgentPlanTransitionResult:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AgentPlanRecord)
                .where(AgentPlanRecord.plan_id == plan_id)
                .with_for_update()
            )
            if record is None:
                return AgentPlanTransitionResult(AgentPlanTransitionOutcome.NOT_FOUND)
            if record.database != actor.database or record.uid != actor.uid:
                return AgentPlanTransitionResult(
                    AgentPlanTransitionOutcome.BINDING_MISMATCH
                )
            if record.state != PlanState.AUTHORIZED.value:
                return AgentPlanTransitionResult(AgentPlanTransitionOutcome.INVALID_STATE)
            is_recovery = record.error_code == RECOVERABLE_EXECUTION_ERROR
            if record.error_code is not None and not is_recovery:
                return AgentPlanTransitionResult(AgentPlanTransitionOutcome.CORRUPT)
            # The original preview TTL prevents stale first execution. Once the exact
            # authorization has already been exercised and only its idempotent batch
            # outcome is unknown, recovery must remain possible without minting fresh
            # authority or rebuilding the plan.
            if not is_recovery and started_at >= record.expires_at:
                record.state = PlanState.EXPIRED.value
                record.state_version += 1
                record.updated_at = started_at
                _audit(session, record, "expired", started_at)
                return AgentPlanTransitionResult(
                    AgentPlanTransitionOutcome.EXPIRED,
                    _snapshot(session, record),
                )
            record.state = PlanState.EXECUTING.value
            record.execution_started_at = started_at
            record.error_code = None
            record.state_version += 1
            record.updated_at = started_at
            session.flush()
            _audit(
                session,
                record,
                "execution_recovery_claimed" if is_recovery else "execution_claimed",
                started_at,
            )
            return AgentPlanTransitionResult(
                AgentPlanTransitionOutcome.APPLIED,
                _snapshot(session, record),
            )

    def prepare_execution_recovery(
        self,
        *,
        plan_id: UUID,
        error_code: str,
        occurred_at: datetime,
    ) -> StoredAgentPlan:
        if error_code != RECOVERABLE_EXECUTION_ERROR:
            raise AgentPlanStoreError("agent_recovery_error_invalid")
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AgentPlanRecord)
                .where(AgentPlanRecord.plan_id == plan_id)
                .with_for_update()
            )
            if (
                record is None
                or record.state != PlanState.EXECUTING.value
                or record.authorization_id is None
                or record.authorization_source is None
                or record.completed_at is not None
            ):
                raise AgentPlanStoreError("agent_plan_invalid_state")
            record.state = PlanState.AUTHORIZED.value
            record.execution_started_at = None
            record.error_code = error_code
            record.state_version += 1
            record.updated_at = occurred_at
            session.flush()
            _audit(session, record, "execution_recovery_pending", occurred_at)
            return _snapshot(session, record)

    def complete(
        self,
        *,
        plan_id: UUID,
        state: PlanState,
        completed_at: datetime,
        error_code: str | None = None,
    ) -> StoredAgentPlan:
        if state not in {PlanState.COMPLETED, PlanState.PARTIAL, PlanState.FAILED}:
            raise AgentPlanStoreError("agent_terminal_state_invalid")
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AgentPlanRecord)
                .where(AgentPlanRecord.plan_id == plan_id)
                .with_for_update()
            )
            if record is None or record.state != PlanState.EXECUTING.value:
                raise AgentPlanStoreError("agent_plan_invalid_state")
            record.state = state.value
            record.completed_at = completed_at
            record.error_code = error_code
            record.state_version += 1
            record.updated_at = completed_at
            session.flush()
            _audit(session, record, state.value, completed_at)
            return _snapshot(session, record)

    def record_step_result(
        self,
        *,
        plan_id: UUID,
        step_id: str,
        state: Literal["completed", "partial", "failed", "skipped"],
        occurred_at: datetime,
        receipt: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> None:
        with session_scope(self._session_factory) as session:
            plan = session.scalar(
                select(AgentPlanRecord)
                .where(AgentPlanRecord.plan_id == plan_id)
                .with_for_update()
            )
            step = session.scalar(
                select(AgentPlanStepRecord)
                .where(
                    AgentPlanStepRecord.plan_id == plan_id,
                    AgentPlanStepRecord.step_id == step_id,
                )
                .with_for_update()
            )
            if (
                plan is None
                or plan.state != PlanState.EXECUTING.value
                or step is None
                or step.state not in {"planned", "previewed"}
            ):
                raise AgentPlanStoreError("agent_plan_step_invalid_state")
            step.state = state
            step.receipt = cast(dict[str, JsonValue] | None, receipt)
            step.error_code = error_code
            step.updated_at = occurred_at
            session.flush()
            _audit(session, plan, f"step_{state}", occurred_at)


def _snapshot(session: Session, record: AgentPlanRecord) -> StoredAgentPlan:
    rows = tuple(
        session.scalars(
            select(AgentPlanStepRecord)
            .where(AgentPlanStepRecord.plan_id == record.plan_id)
            .order_by(AgentPlanStepRecord.position)
        )
    )
    try:
        metadata = AgentPlanMetadata.model_validate(record.metadata_payload)
        policy = EffectiveAgentPolicy.model_validate(record.policy_snapshot)
        steps = tuple(
            AgentPlanStep(
                step_id=row.step_id,
                title=row.title,
                tool_name=row.tool_name,
                arguments=row.arguments,
                depends_on=tuple(row.dependencies),
                risk=RiskLevel(row.risk),
                effect_scope=EffectScope(row.effect_scope),
                is_write=row.is_write,
                is_business_action=row.is_business_action,
                atomic=row.atomic,
                estimated_records=row.estimated_records,
                payload_fingerprint=row.payload_fingerprint,
                proposal_id=row.proposal_id,
                proposal_fingerprint=row.proposal_fingerprint,
            )
            for row in rows
        )
        state = PlanState(record.state)
        risk = RiskLevel(record.risk)
        confidence = AnswerConfidence(record.confidence)
        authorization_source = (
            AuthorizationSource(record.authorization_source)
            if record.authorization_source
            else None
        )
    except (ValidationError, ValueError, TypeError):
        raise AgentPlanStoreError("agent_plan_corrupt") from None
    expected_fingerprint = _plan_fingerprint(cast(dict[str, object], record.canonical_plan))
    actual_canonical = {
        "actor": {"database": record.database, "uid": record.uid},
        "allowed_company_ids": sorted(record.allowed_company_ids),
        "company_id": record.company_id,
        "conversation_id": (
            str(record.conversation_id) if record.conversation_id else None
        ),
        "metadata": metadata.model_dump(mode="json"),
        "plan_id": str(record.plan_id),
        "policy_fingerprint": policy.fingerprint,
        "risk": risk.value,
        "steps": [step.model_dump(mode="json") for step in steps],
        "turn_id": str(record.turn_id),
    }
    if (
        not hmac.compare_digest(expected_fingerprint, record.plan_fingerprint)
        or not hmac.compare_digest(policy.fingerprint, record.policy_fingerprint)
        or not hmac.compare_digest(
            agent_policy_fingerprint(policy), record.policy_fingerprint
        )
        or policy.revision != POLICY_REVISION
        or record.canonical_plan != actual_canonical
        or len(rows) != len(steps)
        or record.state_version < 0
        or not _state_shape_valid(record, state, has_writes=any(step.is_write for step in steps))
    ):
        raise AgentPlanStoreError("agent_plan_corrupt")
    return StoredAgentPlan(
        plan_id=record.plan_id,
        turn_id=record.turn_id,
        conversation_id=record.conversation_id,
        actor=ChatActor(database=record.database, uid=record.uid),
        company_id=record.company_id,
        allowed_company_ids=tuple(record.allowed_company_ids),
        goal=record.goal,
        answer_markdown=record.answer_markdown,
        confidence=confidence,
        assumptions=tuple(record.assumptions),
        state=state,
        risk=risk,
        metadata=metadata,
        policy=policy,
        steps=steps,
        canonical_plan=cast(dict[str, object], record.canonical_plan),
        plan_fingerprint=expected_fingerprint,
        requires_confirmation=record.requires_confirmation,
        expires_at=record.expires_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        authorization_id=record.authorization_id,
        authorization_source=authorization_source,
        decided_by_uid=record.decided_by_uid,
        decided_at=record.decided_at,
        execution_started_at=record.execution_started_at,
        completed_at=record.completed_at,
        error_code=record.error_code,
        state_version=record.state_version,
        step_results=tuple(
            StoredAgentPlanStepResult(
                step_id=row.step_id,
                state=cast(
                    Literal[
                        "planned",
                        "previewed",
                        "executing",
                        "completed",
                        "partial",
                        "failed",
                        "skipped",
                    ],
                    row.state,
                ),
                receipt=cast(dict[str, object] | None, row.receipt),
                error_code=row.error_code,
                updated_at=row.updated_at,
            )
            for row in rows
        ),
    )


def _state_shape_valid(
    record: AgentPlanRecord, state: PlanState, *, has_writes: bool
) -> bool:
    if state is PlanState.AWAITING_CONFIRMATION:
        return (
            record.requires_confirmation
            and record.authorization_id is None
            and record.decided_at is None
        )
    if state is PlanState.AUTHORIZED:
        return (
            record.authorization_id is not None
            and record.authorization_source is not None
            and record.requires_confirmation
            == (
                record.authorization_source
                == AuthorizationSource.USER_CONFIRMATION.value
            )
            and record.execution_started_at is None
            and record.completed_at is None
            and record.error_code in {None, RECOVERABLE_EXECUTION_ERROR}
        )
    if state is PlanState.EXECUTING:
        return (
            record.authorization_id is not None
            and record.authorization_source is not None
            and record.execution_started_at is not None
            and record.completed_at is None
            and record.error_code is None
        )
    if state in {PlanState.COMPLETED, PlanState.PARTIAL, PlanState.FAILED}:
        if record.completed_at is None:
            return False
        return not has_writes or record.authorization_id is not None
    if state is PlanState.REJECTED:
        return record.authorization_id is None and record.completed_at is not None
    return True


def _audit(
    session: Session,
    record: AgentPlanRecord,
    event_type: str,
    occurred_at: datetime,
) -> None:
    session.add(
        AgentPlanAuditRecord(
            plan_id=record.plan_id,
            event_type=event_type,
            state=record.state,
            actor_uid=record.uid,
            plan_fingerprint=record.plan_fingerprint,
            attributes={
                "authorization_source": record.authorization_source,
                "policy_fingerprint": record.policy_fingerprint,
                "risk": record.risk,
                "state_version": record.state_version,
            },
            created_at=occurred_at,
        )
    )
