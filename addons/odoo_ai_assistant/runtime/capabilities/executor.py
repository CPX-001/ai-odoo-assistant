"""Uniform lifecycle execution for discovered capabilities."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping
from dataclasses import replace

from .config import CapabilityConfigResolver
from .contracts import CapabilityContext, CapabilityError, CapabilityResult, JsonValue
from .policy import CapabilityPolicy, ExecutionAuthority
from .registry import CapabilityRegistry
from .validation import validate_payload


class CapabilityExecutor:
    """Resolve → validate → authorize → execute → validate → events."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        context: CapabilityContext,
        *,
        policy: CapabilityPolicy | None = None,
        config: CapabilityConfigResolver | None = None,
    ) -> None:
        self._registry = registry
        self._context = context
        self._policy = policy or CapabilityPolicy()
        self._config = config or CapabilityConfigResolver()
        self._calls: dict[str, int] = {}

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, JsonValue],
        *,
        authority: ExecutionAuthority = ExecutionAuthority.REASONING,
        approved: bool = False,
    ) -> CapabilityResult:
        definition = self._registry.resolve(name)
        if definition not in self._registry.available(self._context):
            raise CapabilityError("capability_not_available")
        decision = self._policy.evaluate(
            definition,
            self._context,
            authority=authority,
            approved=approved,
        )
        if not decision.allowed:
            raise CapabilityError(decision.reason)
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
        resolved_settings = self._config.resolve(definition)
        context = replace(self._context, settings=resolved_settings)
        self._calls[name] = calls + 1
        context.emit(
            "tool.started",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        try:
            raw = definition.handler(context, payload)
            if inspect.isawaitable(raw):
                if definition.timeout_seconds is None:
                    raw = await raw
                else:
                    raw = await asyncio.wait_for(
                        raw,
                        timeout=definition.timeout_seconds,
                    )
        except asyncio.TimeoutError as error:
            context.emit(
                "tool.failed",
                definition.title or definition.name,
                {"capability": definition.name, "code": "capability_timeout"},
            )
            raise CapabilityError("capability_timeout") from error
        except CapabilityError as error:
            context.emit(
                "tool.failed",
                definition.title or definition.name,
                {"capability": definition.name, "code": error.code},
            )
            raise
        except Exception as error:  # noqa: BLE001 - framework boundary sanitizes providers
            context.emit(
                "tool.failed",
                definition.title or definition.name,
                {"capability": definition.name, "code": "capability_handler_failed"},
            )
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
        context.emit(
            "tool.completed",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        return CapabilityResult(
            data=output,
            evidence=result.evidence,
            changes_preconditions=result.changes_preconditions,
        )
