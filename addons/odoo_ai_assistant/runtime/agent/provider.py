"""Provider-neutral decision port consumed by the Odoo-owned agent host loop."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..capabilities import CapabilityContext, CapabilityDefinition
from .contracts import NextDecision


@runtime_checkable
class ReasoningProvider(Protocol):
    """Return one untrusted next decision; Odoo retains all execution authority."""

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
    ) -> NextDecision: ...
