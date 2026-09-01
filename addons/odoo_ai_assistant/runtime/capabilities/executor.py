"""Uniform lifecycle execution for discovered capabilities."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import secrets
import time
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
_PUBLIC_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_PUBLIC_ACTIVITY_ID = re.compile(r"^activity:v1:[0-9a-f]{32}$")
_PUBLIC_SEMANTIC_GROUP = re.compile(r"^semantic:v1:[0-9a-f]{32}$")
_PUBLIC_SEMANTIC_CODE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_MAX_PUBLIC_RECORD_REFS = 50
_MAX_PUBLIC_DISPLAY_NAME = 160
_MAX_PUBLIC_NAV_REFS = 12
_MAX_PUBLIC_SEMANTIC_ARGS = 8
_MAX_PUBLIC_SEMANTIC_BYTES = 2048
_PUBLIC_NAV_KINDS = frozenset(
    {"odoo_model", "odoo_action", "odoo_view", "odoo_menu", "odoo_setting"}
)


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
        *,
        semantic_group_key: str | None = None,
    ) -> CapabilityPreview:
        definition, payload, context = self._prepare(name, arguments)
        if definition.exposure is not CapabilityExposure.PLAN:
            raise CapabilityError("capability_preview_authority_invalid")
        if definition.preview_handler is None:
            raise CapabilityError("capability_preview_unavailable")
        public = _public_operation_payload(
            context,
            definition,
            payload,
            stage="prepare",
            activity_id=_new_activity_id(),
            semantic_group_key=semantic_group_key,
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
            stage="preview",
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
        semantic_group_key: str | None = None,
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
            context,
            definition,
            payload,
            stage="execute",
            activity_id=_new_activity_id(),
            semantic_group_key=semantic_group_key,
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
            stage="execute",
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
        *,
        semantic_group_key: str | None = None,
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
            context,
            definition,
            payload,
            stage="verify",
            activity_id=_new_activity_id(),
            semantic_group_key=semantic_group_key,
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
            stage="verify",
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
        completed_public = _public_verified_payload(public, raw.summary)
        context.emit(
            "tool.verify.completed",
            definition.title or definition.name,
            completed_public,
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
        stage,
        public_payload,
    ):
        started_at = time.monotonic()
        outcome = "ok"
        try:
            raw = handler(context, payload)
            if inspect.isawaitable(raw):
                if timeout_seconds is None:
                    raw = await raw
                else:
                    raw = await asyncio.wait_for(raw, timeout=timeout_seconds)
            return raw
        except TimeoutError as error:
            outcome = "capability_timeout"
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": "capability_timeout"},
            )
            raise CapabilityError("capability_timeout") from error
        except CapabilityError as error:
            outcome = error.code
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": error.code},
            )
            raise
        except Exception as error:
            outcome = "capability_handler_failed"
            context.emit(
                failure_event,
                title,
                {**public_payload, "code": "capability_handler_failed"},
            )
            raise CapabilityError("capability_handler_failed") from error
        finally:
            _emit_capability_timing(
                context,
                capability=capability,
                stage=stage,
                elapsed_ms=round(max(0.0, time.monotonic() - started_at) * 1000, 3),
                outcome=outcome,
            )


def _new_activity_id():
    return f"activity:v1:{secrets.token_hex(16)}"


def _emit_capability_timing(context, *, capability, stage, elapsed_ms, outcome):
    """Persist content-free timing without making diagnostics product authority."""

    try:
        context.emit(
            "diagnostic.capability_timing",
            "Capability timing checkpoint",
            {
                "capability": capability,
                "stage": stage,
                "elapsed_ms": elapsed_ms,
                "outcome": outcome,
            },
        )
    except Exception:  # noqa: BLE001 - timing diagnostics must never fail a product turn
        return


def _public_operation_payload(
    context,
    definition,
    payload,
    *,
    stage,
    activity_id=None,
    semantic_group_key=None,
):
    """Project only schema-validated non-secret resource identifiers into host activity."""

    result = {"capability": definition.name}
    if isinstance(activity_id, str) and _PUBLIC_ACTIVITY_ID.fullmatch(activity_id):
        result["activity_id"] = activity_id
    model = payload.get("model")
    if isinstance(model, str) and _PUBLIC_MODEL.fullmatch(model):
        result["model"] = model
    record_id = payload.get("record_id")
    if type(record_id) is int and record_id > 0:
        result["record_id"] = record_id
    semantic = _semantic_activity(
        context,
        definition,
        payload,
        stage=stage,
        group_key=semantic_group_key,
    )
    if semantic is not None:
        result["semantic"] = semantic
    return result


def _public_result_payload(context, public, output):
    """Project bounded identities only after output-schema validation.

    Navigation references are projected only from the installed ``odoo.resolve_navigation``
    capability result. Their identifiers are therefore host-resolved output, never model-supplied
    authority. Record identities retain the existing same-user display-name re-read.
    """

    result = dict(public)
    semantic = _semantic_result(result.get("semantic"), output, verified=False)
    if semantic is not None:
        result["semantic"] = semantic
    if result.get("capability") == "odoo.resolve_navigation":
        references = _public_navigation_references(output.get("references"))
        if references is not None:
            result["references"] = references

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


def _public_verified_payload(public, summary):
    result = dict(public)
    semantic = _semantic_result(result.get("semantic"), summary, verified=True)
    if semantic is not None:
        result["semantic"] = semantic
    return result


def _semantic_activity(context, definition, payload, *, stage, group_key):
    if group_key is not None and (
        not isinstance(group_key, str) or _PUBLIC_SEMANTIC_GROUP.fullmatch(group_key) is None
    ):
        raise CapabilityError("capability_semantic_group_invalid")
    model = payload.get("model")
    model_label = _public_model_label(context, model)
    operation = payload.get("operation") if isinstance(payload.get("operation"), str) else None
    count = _input_count(payload)
    args = {}
    if model_label:
        args["model_label"] = model_label
    if count is not None:
        args["count"] = count

    activity = definition.activity
    if activity is not None and activity.projector is not None:
        projected = _safe_activity_projection(activity.projector, context, payload)
        args = _merge_semantic_args(args, projected)

    if stage == "verify":
        semantic_operation = "capability.verify"
        headline_code = "activity.verify.results"
    elif stage == "prepare":
        semantic_operation = "capability.prepare"
        headline_code = _mutation_headline("prepare", operation or _operation_from_tags(definition.tags))
    elif activity is not None:
        semantic_operation = activity.operation
        headline_code = activity.headline_code
    elif definition.effect.value != "read-only":
        semantic_operation = "capability.execute"
        headline_code = _mutation_headline("execute", operation or _operation_from_tags(definition.tags))
    elif definition.risk.value == "metadata":
        semantic_operation = "odoo.metadata.inspect"
        headline_code = "activity.inspect.odoo"
    else:
        semantic_operation = "odoo.records.query"
        headline_code = "activity.query.odoo"
    parent = context.metadata.get("semantic_parent_activity_id")
    if not isinstance(parent, str) or _PUBLIC_ACTIVITY_ID.fullmatch(parent) is None:
        parent = None
    return {
        "group_key": group_key,
        "parent_activity_id": parent,
        "operation": semantic_operation,
        "headline_code": headline_code,
        "headline_args": args,
        "progress": None,
        "result_summary": None,
    }


def _safe_activity_projection(projector, context, payload):
    """Fail isolated: presentation code must never become business-operation authority."""

    try:
        value = projector(context, payload)
    except Exception:  # noqa: BLE001 - capability remains executable without presentation hints
        return {}
    if not isinstance(value, Mapping):
        return {}
    return _normalize_semantic_args(value)


def _merge_semantic_args(base, extra):
    merged = dict(base)
    for key, value in extra.items():
        if len(merged) >= _MAX_PUBLIC_SEMANTIC_ARGS and key not in merged:
            break
        merged[key] = value
    normalized = _normalize_semantic_args(merged)
    while len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > _MAX_PUBLIC_SEMANTIC_BYTES:
        if not normalized:
            break
        normalized.pop(next(reversed(normalized)))
    return normalized


def _normalize_semantic_args(value):
    result = {}
    for key, item in value.items():
        if len(result) >= _MAX_PUBLIC_SEMANTIC_ARGS:
            break
        if not isinstance(key, str) or _PUBLIC_FIELD.fullmatch(key) is None:
            continue
        if isinstance(item, str):
            normalized = " ".join(item.split())[:160]
            result[key] = normalized
        elif type(item) is bool or type(item) is int and 0 <= item <= 1_000_000:
            result[key] = item
    return result


def _operation_from_tags(tags):
    for operation in ("create", "patch", "archive", "unarchive", "delete", "confirm"):
        if operation in tags:
            return operation
    return None


def _mutation_headline(stage, operation):
    known = {"create", "patch", "archive", "unarchive", "delete", "confirm"}
    suffix = operation if operation in known else "changes"
    return f"activity.{stage}.{suffix}"


def _input_count(payload):
    if isinstance(payload.get("rows"), list):
        return len(payload["rows"])
    if isinstance(payload.get("records"), list):
        return len(payload["records"])
    if isinstance(payload.get("record_ids"), list):
        return len(payload["record_ids"])
    return 1 if type(payload.get("record_id")) is int else None


def _public_model_label(context, model):
    if not isinstance(model, str) or _PUBLIC_MODEL.fullmatch(model) is None:
        return None
    try:
        model_set = context.env[model]
        label = str(getattr(model_set, "_description", "") or model)
        translator = getattr(context.env, "_", None)
        if callable(translator):
            label = str(translator(label))
    except Exception:  # noqa: BLE001 - presentation remains non-authoritative
        return None
    normalized = " ".join(label.split())
    return normalized[:160] if normalized else None


def _semantic_result(semantic, output, *, verified):
    if not isinstance(semantic, dict) or not isinstance(output, Mapping):
        return None
    result = dict(semantic)
    args = dict(result.get("headline_args") or {})
    count = output.get("count")
    if type(count) is not int:
        count = output.get("returned_count")
    if type(count) is not int and isinstance(output.get("record_ids"), list):
        count = len(output["record_ids"])
    if type(count) is int and 0 <= count <= 1_000_000:
        operation = output.get("operation")
        summary_args = {"count": count}
        if isinstance(args.get("model_label"), str):
            summary_args["model_label"] = args["model_label"]
        if isinstance(operation, str):
            summary_args["operation"] = operation[:64]
        if verified:
            code = "activity.result.verified"
            expected = args.get("count")
            if type(expected) is int and expected == count and expected > 0:
                result["progress"] = {"current": count, "total": expected}
        elif result.get("operation") in {"odoo.records.query", "odoo.records.aggregate"}:
            code = "activity.result.records_found"
        else:
            return result
        result["result_summary"] = {"code": code, "args": summary_args}
    return result


def _public_navigation_references(value):
    if not isinstance(value, list) or len(value) > _MAX_PUBLIC_NAV_REFS:
        return None
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        kind = item.get("kind")
        label = item.get("label")
        description = item.get("description")
        if (
            kind not in _PUBLIC_NAV_KINDS
            or not isinstance(label, str)
            or not 1 <= len(" ".join(label.split())) <= 160
            or not isinstance(description, str)
            or len(" ".join(description.split())) > 240
        ):
            return None
        expected = {
            "odoo_model": {"kind", "label", "description", "model"},
            "odoo_action": {"kind", "label", "description", "model", "action_id"},
            "odoo_view": {"kind", "label", "description", "model", "view_id"},
            "odoo_menu": {
                "kind",
                "label",
                "description",
                "model",
                "action_id",
                "menu_id",
            },
            "odoo_setting": {
                "kind",
                "label",
                "description",
                "model",
                "action_id",
                "setting_field",
            },
        }[kind]
        if set(item) != expected:
            return None
        model = item.get("model")
        if not isinstance(model, str) or _PUBLIC_MODEL.fullmatch(model) is None:
            return None
        normalized = {
            "kind": kind,
            "label": " ".join(label.split()),
            "description": " ".join(description.split()),
            "model": model,
        }
        for key in ("action_id", "view_id", "menu_id"):
            if key not in item:
                continue
            identifier = item.get(key)
            if type(identifier) is not int or identifier <= 0:
                return None
            normalized[key] = identifier
        if "setting_field" in item:
            field = item.get("setting_field")
            if not isinstance(field, str) or _PUBLIC_FIELD.fullmatch(field) is None:
                return None
            normalized["setting_field"] = field
        if kind == "odoo_setting" and model != "res.config.settings":
            return None
        result.append(normalized)
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
