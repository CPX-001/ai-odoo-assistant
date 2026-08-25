"""Declarative decorators used by capability provider modules."""

from __future__ import annotations

from copy import deepcopy

from .contracts import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityDependency,
    CapabilityEffect,
    CapabilityExposure,
    CapabilityGuard,
    CapabilityHandler,
    CapabilityRisk,
    CapabilitySetting,
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
    title: str = "",
    version: str = "1",
    exposure: CapabilityExposure = CapabilityExposure.REASONING,
    approval: CapabilityApproval = CapabilityApproval.NONE,
    tags: tuple[str, ...] = (),
    dependencies: tuple[CapabilityDependency, ...] = (),
    settings: tuple[CapabilitySetting, ...] = (),
    required_groups: tuple[str, ...] = (),
    default_enabled: bool = True,
    timeout_seconds: int | None = None,
    max_calls: int = 4,
    max_input_bytes: int = 16 * 1024,
    max_output_bytes: int = 96 * 1024,
    help_text: str = "",
    audit_metadata: dict[str, JsonValue] | None = None,
    developer_metadata: dict[str, JsonValue] | None = None,
    guard: CapabilityGuard | None = None,
):
    """Attach one complete definition; provider authors do not edit central catalogs."""

    def decorate(handler: CapabilityHandler) -> CapabilityHandler:
        if hasattr(handler, _DEFINITION_ATTR):
            raise RuntimeError("capability_handler_already_decorated")
        definition = CapabilityDefinition(
            name=name,
            title=title,
            description=description,
            input_schema=deepcopy(input_schema),
            output_schema=deepcopy(output_schema),
            risk=risk,
            effect=effect,
            handler=handler,
            version=version,
            exposure=exposure,
            approval=approval,
            tags=tags,
            dependencies=dependencies,
            settings=settings,
            required_groups=required_groups,
            default_enabled=default_enabled,
            timeout_seconds=timeout_seconds,
            max_calls=max_calls,
            max_input_bytes=max_input_bytes,
            max_output_bytes=max_output_bytes,
            help_text=help_text,
            audit_metadata=deepcopy(audit_metadata or {}),
            developer_metadata=deepcopy(developer_metadata or {}),
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
