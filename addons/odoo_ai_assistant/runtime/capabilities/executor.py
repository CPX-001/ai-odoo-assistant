"""Uniform lifecycle execution for discovered capabilities."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import secrets
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

_PUBLIC_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_PUBLIC_ACTIVITY_ID = re.compile(r"^activity:v1:[0-9a-f]{32}$")
_MAX_PUBLIC_RECORD_REFS = 20
_MAX_PUBLIC_DISPLAY_NAME = 160


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
        public = _public_operation_payload(
            definition.name, payload, activity_id=_new_activity_id()
        )
        context.emit(
            "tool.preview.started",
            definition.title or definition.name,
            public,
        )
        raw = await self._invoke(
            definition.preview_handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.preview.failed",
            title=definition.title or definition.name,
            capability=definition.name,
            public_payload=public,
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
            public,
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
        public = _public_operation_payload(
            definition.name, payload, activity_id=_new_activity_id()
        )
        context.emit(
            "tool.started",
            definition.title or definition.name,
            public,
        )
        raw = await self._invoke(
            definition.handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.failed",
            title=definition.title or definition.name,
            capability=definition.name,
            public_payload=public,
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
        completed_public = _public_result_payload(context, public, output)
        context.emit(
            "tool.completed",
            definition.title or definition.name,
            completed_public,
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
        public = _public_operation_payload(
            definition.name, payload, activity_id=_new_activity_id()
        )
        context.emit(
            "tool.verify.started",
            definition.title or definition.name,
            public,
        )
        raw = await self._invoke(
            definition.verify_handler,
            context,
            payload,
            timeout_seconds=definition.timeout_seconds,
            failure_event="tool.verify.failed",
            title=definition.title or definition.name,
            capability=definition.name,
            public_payload=public,
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
                {**public, "code": "capability_verification_failed"},
            )
            raise CapabilityError("capability_verification_failed")
        context.emit(
            "tool.verify.completed",
            definition.title or definition.name,
            public,
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
        public_payload,
    ):
        try:
            raw = handler(context, payload)
            if inspect.isawaitable(raw):
                if timeout_seconds is None:
                    raw = await raw
                else:
                    raw = await asyncio.wait_for(raw, timeout=timeout_seconds)
            return raw
        except TimeoutError as error:
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": "capability_timeout"},
            )
            raise CapabilityError("capability_timeout") from error
        except CapabilityError as error:
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": error.code},
            )
            raise
        except Exception as error:  # noqa: BLE001 - framework boundary sanitizes providers
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": "capability_handler_failed"},
            )
            raise CapabilityError("capability_handler_failed") from error


def _new_activity_id():
    return f"activity:v1:{secrets.token_hex(16)}"


def _public_operation_payload(name, payload, *, activity_id=None):
    """Project only schema-validated non-secret resource identifiers into host activity.

    The capability name and title come from trusted installed ``CapabilityDefinition`` code.
    ``model``/``record_id`` are copied only after the input schema has validated the payload;
    arbitrary arguments, filters, values, tool results and display names never cross this seam.
    ``activity_id`` is host-generated correlation metadata and never originates from model arguments.
    """

    result = {"capability": name}
    if isinstance(activity_id, str) and _PUBLIC_ACTIVITY_ID.fullmatch(activity_id):
        result["activity_id"] = activity_id
    model = payload.get("model")
    if isinstance(model, str) and _PUBLIC_MODEL.fullmatch(model):
        result["model"] = model
    record_id = payload.get("record_id")
    if type(record_id) is int and record_id > 0:
        result["record_id"] = record_id
    return result


def _public_result_payload(context, public, output):
    """Project bounded result identities only after output-schema validation.

    The optional projection is still re-read under the same effective Odoo user before display
    names are attached. It never changes capability success and never grants navigation authority;
    the browser revalidates a typed reference again immediately before opening it.
    """

    result = dict(public)
    operation_model = result.get("model")
    output_model = output.get("model")
    if isinstance(output_model, str) and _PUBLIC_MODEL.fullmatch(output_model):
        if operation_model is not None and output_model != operation_model:
            return result
        result["model"] = output_model
        operation_model = output_model
    if not isinstance(operation_model, str):
        return result

    ids = []
    raw_record_ids = output.get("record_ids")
    if isinstance(raw_record_ids, list):
        candidates = raw_record_ids
    elif type(output.get("record_id")) is int:
        candidates = [output["record_id"]]
    else:
        raw_records = output.get("records")
        if not isinstance(raw_records, list):
            return result
        candidates = []
        for row in raw_records:
            if not isinstance(row, Mapping):
                return result
            candidates.append(row.get("id"))

    for record_id in candidates[:_MAX_PUBLIC_RECORD_REFS]:
        if type(record_id) is not int or record_id <= 0 or record_id in ids:
            return result
        ids.append(record_id)
    if not ids:
        return result

    try:
        records = context.env[operation_model].browse(ids).exists()
        if records.ids != ids:
            return result
        records.check_access("read")
        names = []
        for record in records:
            name = " ".join(str(record.display_name or "").split())
            if not name:
                name = f"#{record.id}"
            names.append(name[:_MAX_PUBLIC_DISPLAY_NAME])
    except Exception:  # noqa: BLE001 - presentation projection never controls business success
        return result
    result["record_ids"] = ids
    result["display_names"] = names
    return result


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
