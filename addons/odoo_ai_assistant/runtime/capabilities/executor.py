"""Uniform lifecycle execution for discovered capabilities."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from dataclasses import replace

from .config import CapabilityConfigResolver
from .contracts import (
    CapabilityContext,
    CapabilityError,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityResult,
    CapabilityVerification,
    JsonValue,
)
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
        self._config = config or CapabilityConfigResolver.from_env(context.env)
        self._calls: dict[str, int] = {}

    async def preview(
        self,
        name: str,
        arguments: Mapping[str, JsonValue],
    ) -> CapabilityPreview:
        definition, payload, context = self._prepare(name, arguments)
        if definition.exposure is not CapabilityExposure.PLAN:
            raise CapabilityError("capability_preview_authority_invalid")
        if definition.preview_handler is None:
            raise CapabilityError("capability_preview_unavailable")
        context.emit(
            "tool.preview.started",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        raw = await self._invoke(
            definition.preview_handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.preview.failed",
            title=definition.title or definition.name,
            capability=definition.name,
        )
        if not isinstance(raw, CapabilityPreview):
            raise CapabilityError("capability_preview_invalid")
        _validate_bounded_mapping(
            raw.summary,
            maximum=definition.max_output_bytes,
            code="capability_preview_invalid",
        )
        context.emit(
            "tool.preview.completed",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        return CapabilityPreview(
            summary=dict(raw.summary),
            precondition_fingerprint=raw.precondition_fingerprint,
        )

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, JsonValue],
        *,
        authority: ExecutionAuthority = ExecutionAuthority.REASONING,
        approved: bool = False,
    ) -> CapabilityResult:
        definition, payload, context = self._prepare(name, arguments)
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
        self._calls[name] = calls + 1
        context.emit(
            "tool.started",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        raw = await self._invoke(
            definition.handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.failed",
            title=definition.title or definition.name,
            capability=definition.name,
        )
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

    async def verify(
        self,
        name: str,
        arguments: Mapping[str, JsonValue],
        result: CapabilityResult,
    ) -> CapabilityVerification:
        definition, payload, context = self._prepare(name, arguments)
        if definition.exposure is not CapabilityExposure.PLAN:
            raise CapabilityError("capability_verify_authority_invalid")
        if definition.verify_handler is None:
            raise CapabilityError("capability_verify_unavailable")
        metadata = dict(context.metadata)
        metadata["capability_result"] = dict(result.data)
        context = replace(context, metadata=metadata)
        context.emit(
            "tool.verify.started",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        raw = await self._invoke(
            definition.verify_handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.verify.failed",
            title=definition.title or definition.name,
            capability=definition.name,
        )
        if not isinstance(raw, CapabilityVerification):
            raise CapabilityError("capability_verification_invalid")
        _validate_bounded_mapping(
            raw.summary,
            maximum=definition.max_output_bytes,
            code="capability_verification_invalid",
        )
        if not raw.verified:
            context.emit(
                "tool.verify.failed",
                definition.title or definition.name,
                {"capability": definition.name, "code": "capability_verification_failed"},
            )
            raise CapabilityError("capability_verification_failed")
        context.emit(
            "tool.verify.completed",
            definition.title or definition.name,
            {"capability": definition.name},
        )
        return CapabilityVerification(verified=True, summary=dict(raw.summary))

    def approval_required(self, name: str, *, approved: bool = False) -> bool:
        definition = self._registry.resolve(name)
        if definition not in self._registry.available(self._context):
            raise CapabilityError("capability_not_available")
        decision = self._policy.evaluate(
            definition,
            self._context,
            authority=ExecutionAuthority.PLAN,
            approved=approved,
        )
        return decision.requires_approval

    def _prepare(self, name, arguments):
        definition = self._registry.resolve(name)
        if definition not in self._registry.available(self._context):
            raise CapabilityError("capability_not_available")
        payload = dict(arguments)
        validate_payload(
            payload,
            definition.input_schema,
            max_bytes=definition.max_input_bytes,
            error_code="capability_input_invalid",
        )
        resolved_settings = self._config.resolve(definition)
        context = replace(self._context, settings=resolved_settings)
        return definition, payload, context

    async def _invoke(
        self,
        handler,
        context,
        payload,
        *,
        timeout_seconds,
        failure_event,
        title,
        capability,
    ):
        try:
            raw = handler(context, payload)
            if inspect.isawaitable(raw):
                if timeout_seconds is None:
                    raw = await raw
                else:
                    raw = await asyncio.wait_for(raw, timeout=timeout_seconds)
            return raw
        except asyncio.TimeoutError as error:
            context.emit(
                failure_event,
                title,
                {"capability": capability, "code": "capability_timeout"},
            )
            raise CapabilityError("capability_timeout") from error
        except CapabilityError as error:
            context.emit(
                failure_event,
                title,
                {"capability": capability, "code": error.code},
            )
            raise
        except Exception as error:  # noqa: BLE001 - framework boundary sanitizes providers
            context.emit(
                failure_event,
                title,
                {"capability": capability, "code": "capability_handler_failed"},
            )
            raise CapabilityError("capability_handler_failed") from error


def _validate_bounded_mapping(value, *, maximum, code):
    if not isinstance(value, Mapping):
        raise CapabilityError(code)
    try:
        encoded = json.dumps(
            dict(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapabilityError(code) from None
    if len(encoded) > maximum:
        raise CapabilityError(f"{code}_too_large")
