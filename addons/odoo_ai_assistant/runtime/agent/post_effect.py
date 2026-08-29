"""Post-effect provider boundary for natural final answer synthesis.

A verified effect may be followed by more READ reasoning and a natural final answer, but the
provider must not acquire another PLAN opportunity from the already-authorized turn. This
adapter removes the planning catalog and rejects any plan proposal returned anyway.
"""

from __future__ import annotations

from ..capabilities import CapabilityContext, CapabilityDefinition
from .contracts import NextDecision, PlanStepProposal
from .decision_validation import NextDecisionValidationError
from .service import NextDecisionEngine


class PostEffectDecisionEngine:
    """Allow read/final decisions after verification while forbidding another effect proposal."""

    def __init__(self, provider: NextDecisionEngine) -> None:
        self._provider = provider

    async def next_decision(
        self,
        *,
        message: str,
        conversation_summary: str,
        context: CapabilityContext,
        reasoning_capabilities: tuple[CapabilityDefinition, ...],
        planning_capabilities: tuple[CapabilityDefinition, ...],
        working_items: tuple[dict[str, object], ...],
        remaining_budgets: dict[str, int],
    ) -> NextDecision:
        if not any(item.get("kind") == "verified_effect_receipt" for item in working_items):
            raise NextDecisionValidationError("agent_post_effect_receipt_missing")
        decision = await self._provider.next_decision(
            message=message,
            conversation_summary=conversation_summary,
            context=context,
            reasoning_capabilities=reasoning_capabilities,
            planning_capabilities=(),
            working_items=working_items,
            remaining_budgets=remaining_budgets,
        )
        if isinstance(decision, PlanStepProposal):
            raise NextDecisionValidationError(
                "agent_plan_capability_not_allowed",
                decision,
            )
        return decision
