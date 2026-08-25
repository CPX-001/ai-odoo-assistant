"""Codex translation boundary for the transport-neutral capability catalog."""

from __future__ import annotations

from ..contracts import CapabilityContext, JsonValue
from ..registry import CapabilityRegistry


def codex_reasoning_tools(
    registry: CapabilityRegistry,
    context: CapabilityContext,
) -> tuple[dict[str, JsonValue], ...]:
    """Only directly callable reasoning capabilities become Codex function tools."""

    return tuple(
        {
            "name": definition.name,
            "description": definition.description,
            "input_schema": dict(definition.input_schema),
        }
        for definition in registry.for_reasoning(context)
    )


def codex_plan_catalog(
    registry: CapabilityRegistry,
    context: CapabilityContext,
) -> tuple[dict[str, JsonValue], ...]:
    """Plan-only capabilities are describable to planning, never callable tools."""

    return tuple(
        definition.wire_descriptor()
        for definition in registry.for_planning(context)
    )
