"""Declarative decorators used by capability provider modules."""

from __future__ import annotations

from copy import deepcopy

from .contracts import (
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityGuard,
    CapabilityHandler,
    CapabilityRisk,
    JsonValue,
)

_DEFINITION_ATTR = "__odoo_ai_capability_definition__"


def tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, JsonValue],
    output_schema: dict[str, JsonValue],
    risk: CapabilityRisk = CapabilityRisk.READ,
    effect: CapabilityEffect = CapabilityEffect.READ_ONLY,
    version: str = "1",
    tags: tuple[str, ...] = (),
    required_groups: tuple[str, ...] = (),
    default_enabled: bool = True,
    approval_required: bool = False,
    max_calls: int = 4,
    max_input_bytes: int = 16 * 1024,
    max_output_bytes: int = 96 * 1024,
    guard: CapabilityGuard | None = None,
):
    """Attach a complete capability definition to one handler function.

    Provider authors add a new ``*.py`` file and decorate a function. They do not
    update a central registry or any Odoo model relation.
    """

    def decorate(handler: CapabilityHandler) -> CapabilityHandler:
        if hasattr(handler, _DEFINITION_ATTR):
            raise RuntimeError("capability_handler_already_decorated")
        definition = CapabilityDefinition(
            name=name,
            description=description,
            input_schema=deepcopy(input_schema),
            output_schema=deepcopy(output_schema),
            risk=risk,
            effect=effect,
            handler=handler,
            version=version,
            tags=tags,
            required_groups=required_groups,
            default_enabled=default_enabled,
            approval_required=approval_required,
            max_calls=max_calls,
            max_input_bytes=max_input_bytes,
            max_output_bytes=max_output_bytes,
            guard=guard,
            source_module=handler.__module__,
            source_qualname=handler.__qualname__,
        )
        setattr(handler, _DEFINITION_ATTR, definition)
        return handler

    return decorate


def definition_from_object(value: object) -> CapabilityDefinition | None:
    definition = getattr(value, _DEFINITION_ATTR, None)
    return definition if isinstance(definition, CapabilityDefinition) else None
