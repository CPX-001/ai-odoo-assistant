"""Host-side validation for provider-neutral NextDecision values."""

from __future__ import annotations

from ..capabilities.contracts import CapabilityDefinition, CapabilityError
from ..capabilities.validation import validate_payload
from .contracts import (
    FinalAnswer,
    NextDecision,
    PlanStepProposal,
    ReasoningCapabilityCall,
    TaskPlanUpdate,
)
from .task_plan import parse_task_plan


class NextDecisionValidationError(RuntimeError):
    def __init__(self, code: str, decision: NextDecision | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.decision = decision


def validate_next_decision(
    decision: NextDecision,
    *,
    reasoning_capabilities: tuple[CapabilityDefinition, ...],
    planning_capabilities: tuple[CapabilityDefinition, ...],
) -> NextDecision:
    """Resolve one untrusted provider decision against the effective catalog without execution."""

    if isinstance(decision, FinalAnswer):
        return decision
    if isinstance(decision, TaskPlanUpdate):
        try:
            plan = parse_task_plan(decision.task_plan.payload())
        except Exception as error:
            code = getattr(error, "code", "agent_task_plan_invalid")
            raise NextDecisionValidationError(code, decision) from error
        return TaskPlanUpdate(kind=decision.kind, task_plan=plan)
    if isinstance(decision, ReasoningCapabilityCall):
        definition = _allowed(decision.capability, reasoning_capabilities)
        if definition is None:
            raise NextDecisionValidationError(
                "agent_reasoning_capability_not_allowed",
                decision,
            )
        try:
            validate_payload(
                decision.arguments,
                definition.input_schema,
                max_bytes=definition.max_input_bytes,
                error_code="agent_capability_arguments_invalid",
            )
        except CapabilityError as error:
            raise NextDecisionValidationError(error.code, decision) from error
        return ReasoningCapabilityCall(
            kind=decision.kind,
            call_id=decision.call_id,
            capability=definition.name,
            arguments=dict(decision.arguments),
        )
    if isinstance(decision, PlanStepProposal):
        definition = _allowed(decision.capability, planning_capabilities)
        if definition is None:
            raise NextDecisionValidationError(
                "agent_plan_capability_not_allowed",
                decision,
            )
        try:
            validate_payload(
                decision.arguments,
                definition.input_schema,
                max_bytes=definition.max_input_bytes,
                error_code="agent_plan_arguments_invalid",
            )
        except CapabilityError as error:
            raise NextDecisionValidationError(error.code, decision) from error
        return PlanStepProposal(
            kind=decision.kind,
            call_id=decision.call_id,
            capability=definition.name,
            arguments=dict(decision.arguments),
            user_summary=" ".join(decision.user_summary.split()),
        )
    raise NextDecisionValidationError("agent_next_decision_invalid", decision)


def _allowed(name: str, definitions: tuple[CapabilityDefinition, ...]):
    return next((definition for definition in definitions if definition.name == name), None)
