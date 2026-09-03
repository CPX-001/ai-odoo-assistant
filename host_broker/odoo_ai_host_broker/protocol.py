"""Versioned bounded wire contract for the optional local host broker."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping
from typing import Any

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024
MAX_REQUEST_LIFETIME_SECONDS = 300

_REQUEST_ID_RE = re.compile(r"^req:v1:[0-9a-f]{32,64}$")
_RECEIPT_ID_RE = re.compile(r"^receipt:v1:[0-9a-f]{32,64}$")
_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CAPABILITY_RE = _OPERATION_RE
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,128}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ERROR_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_PHASES = frozenset({"preview", "execute", "verify"})
_STATUSES = frozenset({"ok", "denied", "stale", "error", "uncertain"})
_EFFECT_STATES = frozenset({"none", "applied", "unknown"})
_RECOVERY = frozenset({"none", "backup_available", "external_or_unknown"})

_REQUEST_KEYS = {
    "protocol_version",
    "request_id",
    "operation",
    "phase",
    "issued_at",
    "expires_at",
    "binding",
    "payload",
}
_BINDING_KEYS = {
    "turn_id",
    "conversation_id",
    "odoo_uid",
    "database_fingerprint",
    "capability",
    "step_id",
    "args_sha256",
    "binding_fingerprint",
    "precondition_fingerprint",
}
_RECEIPT_KEYS = {
    "protocol_version",
    "request_id",
    "receipt_id",
    "operation",
    "phase",
    "status",
    "effect_state",
    "precondition_fingerprint",
    "postcondition_fingerprint",
    "summary",
    "recovery",
    "error_code",
    "started_at",
    "completed_at",
}


class BrokerProtocolError(RuntimeError):
    """Sanitized wire-contract failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BrokerProtocolError("broker_json_invalid") from error


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def validate_request(value: Any, *, now: int | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise BrokerProtocolError("broker_request_invalid")
    if value.get("protocol_version") != PROTOCOL_VERSION:
        raise BrokerProtocolError("broker_protocol_unsupported")
    request_id = value.get("request_id")
    operation = value.get("operation")
    phase = value.get("phase")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise BrokerProtocolError("broker_request_id_invalid")
    if not isinstance(operation, str) or _OPERATION_RE.fullmatch(operation) is None:
        raise BrokerProtocolError("broker_operation_invalid")
    if phase not in _PHASES:
        raise BrokerProtocolError("broker_phase_invalid")
    issued_at = value.get("issued_at")
    expires_at = value.get("expires_at")
    if type(issued_at) is not int or type(expires_at) is not int:
        raise BrokerProtocolError("broker_request_time_invalid")
    current = int(time.time()) if now is None else now
    if (
        expires_at <= issued_at
        or expires_at - issued_at > MAX_REQUEST_LIFETIME_SECONDS
        or current > expires_at
        or issued_at > current + 30
    ):
        raise BrokerProtocolError("broker_request_expired")

    binding = value.get("binding")
    if not isinstance(binding, dict) or set(binding) != _BINDING_KEYS:
        raise BrokerProtocolError("broker_binding_invalid")
    _validate_binding(binding)

    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise BrokerProtocolError("broker_payload_invalid")
    if len(canonical_json(payload)) > MAX_PAYLOAD_BYTES:
        raise BrokerProtocolError("broker_payload_too_large")
    if binding.get("capability") != operation or binding.get("args_sha256") != canonical_sha256(payload):
        raise BrokerProtocolError("broker_binding_invalid")
    effect_binding = (
        binding.get("step_id"),
        binding.get("binding_fingerprint"),
        binding.get("precondition_fingerprint"),
    )
    if phase == "execute":
        if any(item is None for item in effect_binding):
            raise BrokerProtocolError("broker_binding_invalid")
    elif any(item is not None for item in effect_binding):
        raise BrokerProtocolError("broker_binding_invalid")
    if len(canonical_json(value)) > MAX_REQUEST_BYTES:
        raise BrokerProtocolError("broker_request_too_large")
    return value


def _validate_binding(binding: Mapping[str, Any]) -> None:
    turn_id = binding.get("turn_id")
    conversation_id = binding.get("conversation_id")
    step_id = binding.get("step_id")
    if not isinstance(turn_id, str) or _SAFE_ID_RE.fullmatch(turn_id) is None:
        raise BrokerProtocolError("broker_binding_invalid")
    if conversation_id is not None and (
        not isinstance(conversation_id, str)
        or _SAFE_ID_RE.fullmatch(conversation_id) is None
    ):
        raise BrokerProtocolError("broker_binding_invalid")
    if step_id is not None and (
        not isinstance(step_id, str) or _SAFE_ID_RE.fullmatch(step_id) is None
    ):
        raise BrokerProtocolError("broker_binding_invalid")
    uid = binding.get("odoo_uid")
    if type(uid) is not int or uid <= 0:
        raise BrokerProtocolError("broker_binding_invalid")
    capability = binding.get("capability")
    if not isinstance(capability, str) or _CAPABILITY_RE.fullmatch(capability) is None:
        raise BrokerProtocolError("broker_binding_invalid")
    for key in ("database_fingerprint", "args_sha256"):
        value = binding.get(key)
        if not isinstance(value, str) or _FINGERPRINT_RE.fullmatch(value) is None:
            raise BrokerProtocolError("broker_binding_invalid")
    for key in ("binding_fingerprint", "precondition_fingerprint"):
        value = binding.get(key)
        if value is not None and (
            not isinstance(value, str) or _FINGERPRINT_RE.fullmatch(value) is None
        ):
            raise BrokerProtocolError("broker_binding_invalid")


def validate_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
        raise BrokerProtocolError("broker_receipt_invalid")
    if value.get("protocol_version") != PROTOCOL_VERSION:
        raise BrokerProtocolError("broker_receipt_invalid")
    if (
        not isinstance(value.get("request_id"), str)
        or _REQUEST_ID_RE.fullmatch(value["request_id"]) is None
        or not isinstance(value.get("receipt_id"), str)
        or _RECEIPT_ID_RE.fullmatch(value["receipt_id"]) is None
        or not isinstance(value.get("operation"), str)
        or _OPERATION_RE.fullmatch(value["operation"]) is None
        or value.get("phase") not in _PHASES
        or value.get("status") not in _STATUSES
        or value.get("effect_state") not in _EFFECT_STATES
    ):
        raise BrokerProtocolError("broker_receipt_invalid")
    for key in ("precondition_fingerprint", "postcondition_fingerprint"):
        item = value.get(key)
        if item is not None and (
            not isinstance(item, str) or _FINGERPRINT_RE.fullmatch(item) is None
        ):
            raise BrokerProtocolError("broker_receipt_invalid")
    summary = value.get("summary")
    if not isinstance(summary, dict) or len(canonical_json(summary)) > MAX_PAYLOAD_BYTES:
        raise BrokerProtocolError("broker_receipt_invalid")
    recovery = value.get("recovery")
    if (
        not isinstance(recovery, dict)
        or set(recovery) != {"classification", "token"}
        or recovery.get("classification") not in _RECOVERY
        or (
            recovery.get("token") is not None
            and (
                not isinstance(recovery["token"], str)
                or len(recovery["token"]) > 160
                or "\x00" in recovery["token"]
            )
        )
    ):
        raise BrokerProtocolError("broker_receipt_invalid")
    error_code = value.get("error_code")
    if error_code is not None and (
        not isinstance(error_code, str) or _ERROR_RE.fullmatch(error_code) is None
    ):
        raise BrokerProtocolError("broker_receipt_invalid")
    if type(value.get("started_at")) is not int or type(value.get("completed_at")) is not int:
        raise BrokerProtocolError("broker_receipt_invalid")
    if value["completed_at"] < value["started_at"]:
        raise BrokerProtocolError("broker_receipt_invalid")
    if len(canonical_json(value)) > MAX_RESPONSE_BYTES:
        raise BrokerProtocolError("broker_receipt_invalid")
    return value


__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "PROTOCOL_VERSION",
    "BrokerProtocolError",
    "canonical_json",
    "canonical_sha256",
    "validate_receipt",
    "validate_request",
]
