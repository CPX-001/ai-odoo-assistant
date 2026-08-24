"""Host-owned state machine for immutable grouped agent plans."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from odoo_ai.application.agent_policy import EvaluatedAgentPlan
from odoo_ai.contracts import (
    AgentCandidateOutput,
    AgentPlanDecisionRequest,
    AgentPlanDecisionResponse,
    AgentPlanExecutionRequest,
    AgentPlanReceiptView,
    AgentPlanStatusResponse,
    AgentPlanStepView,
    AgentPlanView,
    AgentPolicyView,
    AgentTurnRequest,
    AuthorizationSource,
    PlanState,
)
from odoo_ai.ports.agent_plans import (
    AgentPlanStore,
    AgentPlanTransitionOutcome,
    StoredAgentPlan,
)

PLAN_TTL = timedelta(minutes=10)
Clock = Callable[[], datetime]


class AgentPlanError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class AgentPlanService:
    def __init__(
        self,
        store: AgentPlanStore,
        *,
        clock: Clock = lambda: datetime.now(UTC),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._clock = clock
        self._id_factory = id_factory

    def create(
        self,
        *,
        request: AgentTurnRequest,
        candidate: AgentCandidateOutput,
        evaluated: EvaluatedAgentPlan,
    ) -> StoredAgentPlan:
        now = self._now()
        plan_id = self._id_factory()
        writes = any(step.is_write for step in evaluated.steps)
        if not writes:
            state = PlanState.COMPLETED
            authorization_id = None
            authorization_source = None
            completed_at = now
        elif evaluated.requires_confirmation:
            state = PlanState.AWAITING_CONFIRMATION
            authorization_id = None
            authorization_source = None
            completed_at = None
        else:
            state = PlanState.AUTHORIZED
            authorization_id = self._id_factory()
            authorization_source = AuthorizationSource.EFFECTIVE_POLICY
            completed_at = None
        canonical = {
            "actor": request.actor.model_dump(mode="json"),
            "allowed_company_ids": sorted(request.user.allowed_company_ids),
            "company_id": request.user.company_id,
            "conversation_id": str(request.conversation_id) if request.conversation_id else None,
            "metadata": evaluated.metadata.model_dump(mode="json"),
            "plan_id": str(plan_id),
            "policy_fingerprint": evaluated.policy.fingerprint,
            "risk": evaluated.risk.value,
            "steps": [step.model_dump(mode="json") for step in evaluated.steps],
            "turn_id": str(request.turn_id),
        }
        plan = StoredAgentPlan(
            plan_id=plan_id,
            turn_id=request.turn_id,
            conversation_id=request.conversation_id,
            actor=request.actor,
            company_id=request.user.company_id,
            allowed_company_ids=tuple(sorted(request.user.allowed_company_ids)),
            goal=candidate.answer_markdown[:1_000],
            answer_markdown=candidate.answer_markdown,
            confidence=candidate.confidence,
            assumptions=candidate.assumptions,
            state=state,
            risk=evaluated.risk,
            metadata=evaluated.metadata,
            policy=evaluated.policy,
            steps=evaluated.steps,
            canonical_plan=canonical,
            plan_fingerprint=_plan_fingerprint(canonical),
            requires_confirmation=evaluated.requires_confirmation,
            authorization_id=authorization_id,
            authorization_source=authorization_source,
            expires_at=now + PLAN_TTL,
            created_at=now,
            updated_at=now,
            completed_at=completed_at,
        )
        self._store.create(plan)
        return plan

    def decide(self, request: AgentPlanDecisionRequest) -> AgentPlanDecisionResponse:
        now = self._now()
        approval = request.decision == "approve"
        authorization_id = self._id_factory() if approval else None
        result = self._store.decide(
            plan_id=request.plan_id,
            actor=request.actor,
            approve=approval,
            authorization_id=authorization_id,
            decided_at=now,
        )
        plan = _transition_plan(result.outcome, result.plan)
        response_state: Literal[PlanState.AUTHORIZED, PlanState.REJECTED]
        response_state = PlanState.AUTHORIZED if approval else PlanState.REJECTED
        return AgentPlanDecisionResponse(
            plan_id=plan.plan_id,
            state=response_state,
            authorization_id=authorization_id,
            decided_at=now,
        )

    def get_status(self, plan_id: UUID, actor_database: str, actor_uid: int) -> AgentPlanStatusResponse:
        plan = self._store.get(plan_id)
        if plan is None:
            raise AgentPlanError("agent_plan_not_found", 404)
        if plan.actor.database != actor_database or plan.actor.uid != actor_uid:
            raise AgentPlanError("agent_plan_binding_mismatch", 403)
        return AgentPlanStatusResponse(
            plan=_view(plan),
            answer_markdown=plan.answer_markdown,
            error_code=plan.error_code,
            completed_at=plan.completed_at,
        )

    def claim_execution(self, request: AgentPlanExecutionRequest) -> StoredAgentPlan:
        result = self._store.claim_execution(
            plan_id=request.plan_id,
            actor=request.actor,
            started_at=self._now(),
        )
        plan = _transition_plan(result.outcome, result.plan)
        if plan.authorization_id is None or plan.authorization_source is None:
            raise AgentPlanError("agent_plan_authorization_missing", 503)
        return plan

    def complete(
        self,
        *,
        plan_id: UUID,
        state: PlanState,
        error_code: str | None = None,
    ) -> StoredAgentPlan:
        try:
            return self._store.complete(
                plan_id=plan_id,
                state=state,
                completed_at=self._now(),
                error_code=error_code,
            )
        except Exception as error:
            code = getattr(error, "code", "agent_plan_store_unavailable")
            raise AgentPlanError(str(code), 503) from None

    def record_step_result(
        self,
        *,
        plan_id: UUID,
        step_id: str,
        state: Literal["completed", "failed", "skipped"],
        receipt: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> None:
        try:
            self._store.record_step_result(
                plan_id=plan_id,
                step_id=step_id,
                state=state,
                occurred_at=self._now(),
                receipt=receipt,
                error_code=error_code,
            )
        except Exception as error:
            code = getattr(error, "code", "agent_plan_store_unavailable")
            raise AgentPlanError(str(code), 503) from None

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise AgentPlanError("clock_unavailable", 503)
        return now.astimezone(UTC)


def _view(plan: StoredAgentPlan) -> AgentPlanView:
    results = {result.step_id: result for result in plan.step_results}
    step_views: list[AgentPlanStepView] = []
    for step in plan.steps:
        result = results.get(step.step_id)
        receipt_payload = result.receipt if result is not None else None
        receipt = None
        if receipt_payload is not None:
            outcome = receipt_payload.get("state")
            record_model = receipt_payload.get("record_model")
            record_id = receipt_payload.get("record_id")
            evidence_id = receipt_payload.get("evidence_id")
            error_code = receipt_payload.get("error_code")
            parsed_evidence_id = UUID(evidence_id) if isinstance(evidence_id, str) else evidence_id
            valid_pointer = isinstance(record_model, str) and isinstance(
                record_id, int
            ) and not isinstance(record_id, bool)
            parsed_record_model = cast(str, record_model) if valid_pointer else None
            parsed_record_id: int | None = record_id if valid_pointer else None  # type: ignore[assignment]
            if parsed_evidence_id is not None and not isinstance(parsed_evidence_id, UUID):
                raise AgentPlanError("agent_plan_receipt_corrupt", 503)
            receipt = AgentPlanReceiptView(
                outcome=outcome if isinstance(outcome, str) else "unknown",
                record_model=parsed_record_model,
                record_id=parsed_record_id,
                evidence_id=parsed_evidence_id,
                error_code=error_code if isinstance(error_code, str) else None,
            )
        step_views.append(
            AgentPlanStepView(
                step_id=step.step_id,
                title=step.title,
                state=result.state if result is not None else "planned",
                risk=step.risk,
                effect_scope=step.effect_scope,
                receipt=receipt,
            )
        )
    return AgentPlanView(
        plan_id=plan.plan_id,
        state=plan.state,
        risk=plan.risk,
        metadata=plan.metadata,
        policy=AgentPolicyView(
            confirmation_mode=plan.policy.confirmation_mode,
            max_auto_risk=plan.policy.max_auto_risk,
            allow_synthetic_data=plan.policy.allow_synthetic_data,
            constrained_by=plan.policy.constrained_by,
        ),
        goal=plan.goal,
        assumptions=plan.assumptions,
        steps=tuple(step_views),
        requires_confirmation=plan.requires_confirmation,
        expires_at=plan.expires_at if plan.state is PlanState.AWAITING_CONFIRMATION else None,
    )


def agent_plan_view(plan: StoredAgentPlan) -> AgentPlanView:
    return _view(plan)


def _transition_plan(
    outcome: AgentPlanTransitionOutcome, plan: StoredAgentPlan | None
) -> StoredAgentPlan:
    if outcome is AgentPlanTransitionOutcome.NOT_FOUND:
        raise AgentPlanError("agent_plan_not_found", 404)
    if outcome is AgentPlanTransitionOutcome.BINDING_MISMATCH:
        raise AgentPlanError("agent_plan_binding_mismatch", 403)
    if outcome is AgentPlanTransitionOutcome.EXPIRED:
        raise AgentPlanError("agent_plan_expired", 410)
    if outcome is AgentPlanTransitionOutcome.CORRUPT:
        raise AgentPlanError("agent_plan_corrupt", 503)
    if outcome is not AgentPlanTransitionOutcome.APPLIED or plan is None:
        raise AgentPlanError("agent_plan_invalid_state")
    return plan


def _plan_fingerprint(value: dict[str, object]) -> str:
    body = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"agent-plan:v1:sha256:{hashlib.sha256(body).hexdigest()}"
