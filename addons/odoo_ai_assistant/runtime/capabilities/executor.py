"""Uniform in-process execution for discovered capabilities."""

from __future__ import annotations

import inspect
from collections.abc import Mapping

from .contracts import CapabilityContext, CapabilityError, CapabilityResult, JsonValue
from .registry import CapabilityRegistry
from .validation import validate_payload


class CapabilityExecutor:
    """Execute only catalogued capabilities under one effective turn context."""

    def __init__(self, registry: CapabilityRegistry, context: CapabilityContext) -> None:
        self._registry = registry
        self._context = context
        self._calls: dict[str, int] = {}

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, JsonValue],
    ) -> CapabilityResult:
        definition = self._registry.resolve(name)
        if not definition.available_for(self._context):
            raise CapabilityError("capability_not_available")
        calls = self._calls.get(name, 0)
        if calls >= definition.max_calls:
            raise CapabilityError("capability_call_limit_exceeded")
        payload = dict(arguments)
        validate_payload(
            payload,
            definition.input_schema,
            max_bytes=definition.max_input_bytes,
            error_code="capability_input_invalid",
        )
        self._calls[name] = calls + 1
        self._context.emit(
            "tool.started",
            definition.name,
            {"capability": definition.name},
        )
        try:
            raw = definition.handler(self._context, payload)
            if inspect.isawaitable(raw):
                raw = await raw
        except CapabilityError:
            raise
        except Exception as error:  # noqa: BLE001 - capability boundary is sanitized
            raise CapabilityError("capability_handler_failed") from error
        if isinstance(raw, CapabilityResult):
            result = raw
        elif isinstance(raw, Mapping):
            result = CapabilityResult(data=raw)
        else:
            raise CapabilityError("capability_output_invalid")
        output = dict(result.data)
        validate_payload(
            output,
            definition.output_schema,
            max_bytes=definition.max_output_bytes,
            error_code="capability_output_invalid",
        )
        self._context.emit(
            "tool.completed",
            definition.name,
            {"capability": definition.name},
        )
        return CapabilityResult(
            data=output,
            evidence=result.evidence,
            changes_preconditions=result.changes_preconditions,
        )
