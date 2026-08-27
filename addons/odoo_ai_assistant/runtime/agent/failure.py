"""Bounded provider-neutral failure contract for terminal Assistant failures."""

from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass
from typing import TypeAlias

JsonObject: TypeAlias = dict[str, object]

FAILURE_CATEGORIES = frozenset(
    {
        "input",
        "context",
        "authentication",
        "provider_connection",
        "provider_protocol",
        "provider_capacity",
        "provider_output",
        "capability_discovery",
        "capability_input",
        "capability_execution",
        "capability_output",
        "policy",
        "approval",
        "odoo_access",
        "retrieval",
        "write_execution",
        "verification",
        "queue_worker",
        "persistence",
        "cancellation",
        "internal",
    }
)
FAILURE_STAGES = frozenset(
    {
        "input",
        "context",
        "enqueue",
        "queue",
        "runtime",
        "provider",
        "reasoning",
        "capability",
        "retrieval",
        "policy",
        "approval",
        "execution",
        "verification",
        "persistence",
        "cancellation",
        "browser",
        "unknown",
    }
)
FAILURE_COMPONENTS = frozenset({"codex", "queue", "capability", "retrieval", "odoo", "browser"})
FAILURE_RETRYABILITIES = frozenset({"never", "safe", "after_change", "unknown"})
FAILURE_EFFECT_STATES = frozenset({"none", "not_started", "confirmed", "partial", "unknown"})
FAILURE_USER_ACTIONS = frozenset(
    {"retry", "reconnect", "clarify", "request_access", "review", "none"}
)

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_DETAIL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DIAGNOSTIC_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_PROVIDER_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_MAX_SUMMARY = 512
_MAX_DETAILS_BYTES = 4 * 1024
_MAX_DETAILS_DEPTH = 4
_MAX_DETAILS_ITEMS = 32
_MAX_DETAIL_STRING = 1024


class FailureEnvelopeError(RuntimeError):
    def __init__(self, code: str = "failure_envelope_invalid") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FailureEnvelope:
    code: str
    category: str
    stage: str
    component: str
    retryability: str
    effect_state: str
    user_action: str
    safe_summary: str
    safe_details: JsonObject
    diagnostic_id: str
    provider_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or _CODE_RE.fullmatch(self.code) is None:
            raise FailureEnvelopeError()
        if not isinstance(self.category, str) or self.category not in FAILURE_CATEGORIES:
            raise FailureEnvelopeError()
        if not isinstance(self.stage, str) or self.stage not in FAILURE_STAGES:
            raise FailureEnvelopeError()
        if not isinstance(self.component, str) or self.component not in FAILURE_COMPONENTS:
            raise FailureEnvelopeError()
        if not isinstance(self.retryability, str) or self.retryability not in FAILURE_RETRYABILITIES:
            raise FailureEnvelopeError()
        if not isinstance(self.effect_state, str) or self.effect_state not in FAILURE_EFFECT_STATES:
            raise FailureEnvelopeError()
        if not isinstance(self.user_action, str) or self.user_action not in FAILURE_USER_ACTIONS:
            raise FailureEnvelopeError()
        if not isinstance(self.safe_summary, str):
            raise FailureEnvelopeError()
        normalized_summary = " ".join(self.safe_summary.split())
        if not 1 <= len(normalized_summary) <= _MAX_SUMMARY or "\x00" in normalized_summary:
            raise FailureEnvelopeError()
        object.__setattr__(self, "safe_summary", normalized_summary)
        if not isinstance(self.safe_details, dict):
            raise FailureEnvelopeError()
        normalized_details = _safe_details(self.safe_details)
        object.__setattr__(self, "safe_details", normalized_details)
        if (
            not isinstance(self.diagnostic_id, str)
            or _DIAGNOSTIC_ID_RE.fullmatch(self.diagnostic_id) is None
        ):
            raise FailureEnvelopeError()
        if self.provider_code is not None and (
            not isinstance(self.provider_code, str)
            or _PROVIDER_CODE_RE.fullmatch(self.provider_code) is None
        ):
            raise FailureEnvelopeError()


def parse_failure_envelope(value: object) -> FailureEnvelope:
    if not isinstance(value, dict) or set(value) != {
        "code",
        "category",
        "stage",
        "component",
        "retryability",
        "effect_state",
        "user_action",
        "safe_summary",
        "safe_details",
        "diagnostic_id",
        "provider_code",
    }:
        raise FailureEnvelopeError()
    try:
        return FailureEnvelope(
            code=value["code"],
            category=value["category"],
            stage=value["stage"],
            component=value["component"],
            retryability=value["retryability"],
            effect_state=value["effect_state"],
            user_action=value["user_action"],
            safe_summary=value["safe_summary"],
            safe_details=value["safe_details"],
            diagnostic_id=value["diagnostic_id"],
            provider_code=value["provider_code"],
        )
    except (KeyError, TypeError):
        raise FailureEnvelopeError() from None


def failure_envelope_payload(envelope: FailureEnvelope) -> JsonObject:
    if not isinstance(envelope, FailureEnvelope):
        raise FailureEnvelopeError()
    return {
        "code": envelope.code,
        "category": envelope.category,
        "stage": envelope.stage,
        "component": envelope.component,
        "retryability": envelope.retryability,
        "effect_state": envelope.effect_state,
        "user_action": envelope.user_action,
        "safe_summary": envelope.safe_summary,
        "safe_details": dict(envelope.safe_details),
        "diagnostic_id": envelope.diagnostic_id,
        "provider_code": envelope.provider_code,
    }


def failure_envelope_schema() -> JsonObject:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "code": {"type": "string", "pattern": _CODE_RE.pattern, "maxLength": 128},
            "category": {"type": "string", "enum": sorted(FAILURE_CATEGORIES)},
            "stage": {"type": "string", "enum": sorted(FAILURE_STAGES)},
            "component": {"type": "string", "enum": sorted(FAILURE_COMPONENTS)},
            "retryability": {"type": "string", "enum": sorted(FAILURE_RETRYABILITIES)},
            "effect_state": {"type": "string", "enum": sorted(FAILURE_EFFECT_STATES)},
            "user_action": {"type": "string", "enum": sorted(FAILURE_USER_ACTIONS)},
            "safe_summary": {"type": "string", "minLength": 1, "maxLength": _MAX_SUMMARY},
            "safe_details": {
                "type": "object",
                "maxProperties": _MAX_DETAILS_ITEMS,
                "propertyNames": {"pattern": _DETAIL_KEY_RE.pattern},
            },
            "diagnostic_id": {
                "type": "string",
                "pattern": _DIAGNOSTIC_ID_RE.pattern,
                "minLength": 8,
                "maxLength": 128,
            },
            "provider_code": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "string", "pattern": _PROVIDER_CODE_RE.pattern, "maxLength": 64},
                ]
            },
        },
        "required": [
            "code",
            "category",
            "stage",
            "component",
            "retryability",
            "effect_state",
            "user_action",
            "safe_summary",
            "safe_details",
            "diagnostic_id",
            "provider_code",
        ],
    }


@dataclass(frozen=True, slots=True)
class _FailureRoute:
    category: str
    stage: str
    retryability: str
    user_action: str
    safe_summary: str


_PROVIDER_CATEGORY_ROUTES = {
    "unauthorized": _FailureRoute(
        "authentication",
        "provider",
        "after_change",
        "reconnect",
        "El proveedor de razonamiento rechazó la autenticación.",
    ),
    "usageLimitExceeded": _FailureRoute(
        "provider_capacity",
        "provider",
        "after_change",
        "retry",
        "El proveedor de razonamiento alcanzó un límite de uso.",
    ),
    "serverOverloaded": _FailureRoute(
        "provider_capacity",
        "provider",
        "unknown",
        "retry",
        "El proveedor de razonamiento está temporalmente saturado.",
    ),
    "httpConnectionFailed": _FailureRoute(
        "provider_connection",
        "provider",
        "unknown",
        "retry",
        "La conexión con el proveedor de razonamiento falló.",
    ),
    "responseStreamConnectionFailed": _FailureRoute(
        "provider_connection",
        "provider",
        "unknown",
        "retry",
        "La conexión de respuesta con el proveedor de razonamiento falló.",
    ),
    "responseStreamDisconnected": _FailureRoute(
        "provider_connection",
        "provider",
        "unknown",
        "retry",
        "La respuesta del proveedor de razonamiento se interrumpió.",
    ),
    "contextWindowExceeded": _FailureRoute(
        "context",
        "provider",
        "after_change",
        "clarify",
        "El contexto superó el límite que el proveedor puede procesar.",
    ),
    "badRequest": _FailureRoute(
        "provider_protocol",
        "provider",
        "never",
        "review",
        "El proveedor rechazó la petición por un problema de protocolo.",
    ),
    "sandboxError": _FailureRoute(
        "provider_protocol",
        "provider",
        "never",
        "review",
        "El runtime del proveedor no pudo completar su aislamiento de ejecución.",
    ),
    "internalError": _FailureRoute(
        "internal",
        "provider",
        "unknown",
        "retry",
        "El proveedor de razonamiento devolvió un error interno.",
    ),
}
_PROVIDER_CONNECTION_CODES = frozenset(
    {
        "codex_process_eof",
        "codex_process_not_running",
        "codex_read_timeout",
        "codex_runtime_start_failed",
        "codex_stdout_unavailable",
        "codex_write_timeout",
    }
)
_PROVIDER_PROTOCOL_CODES = frozenset(
    {
        "codex_error_event_invalid",
        "codex_initialize_response_invalid",
        "codex_provider_error",
        "codex_server_request_not_allowed",
        "codex_turn_completion_mismatch",
    }
)
_PROVIDER_OUTPUT_CODES = frozenset(
    {
        "agent_next_decision_invalid",
        "agent_next_decision_kind_invalid",
        "codex_answer_invalid",
        "codex_answer_missing",
        "codex_output_schema_invalid",
        "codex_turn_items_invalid",
    }
)


def normalize_provider_failure(
    error: object,
    *,
    component: str,
    effect_state: str,
    diagnostic_id: str | None = None,
) -> FailureEnvelope:
    """Project one provider exception to the bounded host-owned failure contract."""

    if component not in FAILURE_COMPONENTS or effect_state not in FAILURE_EFFECT_STATES:
        raise FailureEnvelopeError()

    raw_code = getattr(error, "code", None)
    code = (
        raw_code
        if isinstance(raw_code, str) and _CODE_RE.fullmatch(raw_code)
        else "agent_reasoning_failed"
    )

    provider_failure = getattr(error, "provider_failure", None)
    provider_category = _safe_provider_code(getattr(provider_failure, "category", None))
    upstream_code = _safe_provider_code(getattr(provider_failure, "upstream_code", None))
    http_status = getattr(provider_failure, "http_status_code", None)
    if type(http_status) is not int or not 100 <= http_status <= 599:
        http_status = None

    route = _provider_failure_route(
        code=code,
        provider_category=provider_category,
        upstream_code=upstream_code,
    )
    provider_retryable = getattr(error, "provider_retryable", False) is True
    retryability = route.retryability
    if (
        provider_category == "serverOverloaded"
        and provider_retryable
        and effect_state in {"none", "not_started"}
    ):
        retryability = "safe"

    safe_details: JsonObject = {}
    if http_status is not None:
        safe_details["http_status"] = http_status
    if upstream_code is not None and upstream_code != provider_category:
        safe_details["upstream_code"] = upstream_code
    if provider_retryable:
        safe_details["provider_retryable"] = True

    provider_code = (
        upstream_code
        if code == "codex_output_schema_invalid" and upstream_code is not None
        else provider_category or upstream_code
    )
    return FailureEnvelope(
        code=code,
        category=route.category,
        stage=route.stage,
        component=component,
        retryability=retryability,
        effect_state=effect_state,
        user_action=route.user_action,
        safe_summary=route.safe_summary,
        safe_details=safe_details,
        diagnostic_id=diagnostic_id or _new_diagnostic_id(),
        provider_code=provider_code,
    )


def _provider_failure_route(
    *,
    code: str,
    provider_category: str | None,
    upstream_code: str | None,
) -> _FailureRoute:
    if code == "agent_cancelled":
        return _FailureRoute(
            "cancellation",
            "cancellation",
            "never",
            "none",
            "La petición fue cancelada antes de completar el razonamiento.",
        )
    if upstream_code == "invalid_json_schema" or code == "codex_output_schema_invalid":
        return _FailureRoute(
            "provider_output",
            "provider",
            "never",
            "review",
            "La salida del proveedor no pudo validarse con el contrato esperado.",
        )
    if provider_category in _PROVIDER_CATEGORY_ROUTES:
        return _PROVIDER_CATEGORY_ROUTES[provider_category]
    if code.startswith("codex_context_"):
        return _FailureRoute(
            "context",
            "provider",
            "after_change",
            "clarify",
            "El contexto enviado al proveedor no pudo procesarse de forma segura.",
        )
    if code in _PROVIDER_CONNECTION_CODES:
        return _FailureRoute(
            "provider_connection",
            "provider",
            "unknown",
            "retry",
            "La conexión con el proveedor de razonamiento no pudo completarse.",
        )
    if (
        code in _PROVIDER_PROTOCOL_CODES
        or code.startswith("codex_event_")
        or code.startswith("codex_response_")
        or code.startswith("codex_server_request_")
    ):
        return _FailureRoute(
            "provider_protocol",
            "provider",
            "never",
            "review",
            "La respuesta del proveedor no cumplió el protocolo esperado.",
        )
    if code in _PROVIDER_OUTPUT_CODES or code.startswith("codex_answer_"):
        return _FailureRoute(
            "provider_output",
            "provider",
            "never",
            "review",
            "La salida del proveedor no pudo validarse con el contrato esperado.",
        )
    return _FailureRoute(
        "internal",
        "provider",
        "unknown",
        "review",
        "El proveedor de razonamiento no pudo completar la petición.",
    )


def _safe_provider_code(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and _PROVIDER_CODE_RE.fullmatch(value) is not None
        else None
    )


def _new_diagnostic_id() -> str:
    return f"diag-{secrets.token_hex(12)}"


def _safe_details(value: JsonObject) -> JsonObject:
    normalized = _safe_json_object(value, depth=0)
    try:
        encoded = json.dumps(
            normalized,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise FailureEnvelopeError() from None
    if len(encoded) > _MAX_DETAILS_BYTES:
        raise FailureEnvelopeError()
    return normalized


def _safe_json_object(value: object, *, depth: int) -> JsonObject:
    if depth > _MAX_DETAILS_DEPTH or not isinstance(value, dict) or len(value) > _MAX_DETAILS_ITEMS:
        raise FailureEnvelopeError()
    normalized: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str) or _DETAIL_KEY_RE.fullmatch(key) is None:
            raise FailureEnvelopeError()
        normalized[key] = _safe_json_value(item, depth=depth + 1)
    return normalized


def _safe_json_value(value: object, *, depth: int) -> object:
    if depth > _MAX_DETAILS_DEPTH:
        raise FailureEnvelopeError()
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FailureEnvelopeError()
        return value
    if isinstance(value, str):
        if len(value) > _MAX_DETAIL_STRING or "\x00" in value:
            raise FailureEnvelopeError()
        return value
    if isinstance(value, list):
        if len(value) > _MAX_DETAILS_ITEMS:
            raise FailureEnvelopeError()
        return [_safe_json_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        return _safe_json_object(value, depth=depth)
    raise FailureEnvelopeError()
