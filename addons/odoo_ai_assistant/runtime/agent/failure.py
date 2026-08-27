"""Bounded provider-neutral failure contract for terminal Assistant failures."""

from __future__ import annotations

import json
import math
import re
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
