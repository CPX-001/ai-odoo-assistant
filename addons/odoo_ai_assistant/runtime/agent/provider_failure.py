"""Normalize provider exceptions before they cross the host reasoning boundary."""

from __future__ import annotations

from ..capabilities import CapabilityContext, CapabilityDefinition
from .contracts import NextDecision
from .decision_validation import NextDecisionValidationError
from .failure import FailureEnvelope, normalize_provider_failure
from .provider import ReasoningProvider
from .service import AgentTurnError


class ProviderFailureError(AgentTurnError):
    """Sanitized provider failure carrying one validated FailureEnvelope."""

    def __init__(self, failure: FailureEnvelope) -> None:
        if not isinstance(failure, FailureEnvelope):
            raise ValueError("provider_failure_envelope_invalid")
        super().__init__(failure.code)
        self.failure = failure


class FailureNormalizingDecisionEngine:
    """Decorate one provider-neutral decision engine with host-owned failure normalization."""

    def __init__(
        self,
        provider: ReasoningProvider,
        *,
        component: str,
        effect_state: str,
    ) -> None:
        self._provider = provider
        self._component = component
        self._effect_state = effect_state

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
        try:
            return await self._provider.next_decision(
                message=message,
                conversation_summary=conversation_summary,
                context=context,
                reasoning_capabilities=reasoning_capabilities,
                planning_capabilities=planning_capabilities,
                working_items=working_items,
                remaining_budgets=remaining_budgets,
            )
        except NextDecisionValidationError:
            # AgentTurnService owns the bounded correction path for invalid provider decisions.
            raise
        except ProviderFailureError:
            raise
        except Exception as error:  # noqa: BLE001 - this is the provider/host failure boundary
            failure = normalize_provider_failure(
                error,
                component=self._component,
                effect_state=self._effect_state,
            )
            raise ProviderFailureError(failure) from error
