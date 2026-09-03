"""Wire validation helpers for the optional local Phase 10 host broker."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import struct
from collections.abc import Mapping
from typing import Any

from .capabilities.contracts import CapabilityError

PROTOCOL_VERSION = 1
DEFAULT_SOCKET = "/run/odoo-ai-host-broker/broker.sock"
DEFAULT_BROKER_UID = 0
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024
PHASES = frozenset({"preview", "execute", "verify"})
_RECEIPT_STATUSES = frozenset({"ok", "denied", "stale", "error", "uncertain"})
_RECEIPT_EFFECT_STATES = frozenset({"none", "applied", "unknown"})
_RECOVERY_CLASSIFICATIONS = frozenset({"none", "backup_available", "external_or_unknown"})
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,128}$")
_RECEIPT_ID_RE = re.compile(r"^receipt:v1:[0-9a-f]{32,64}$")
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def expected_uid_from_environment() -> int:
    raw = os.environ.get("ODOO_AI_ASSISTANT_HOST_BROKER_UID")
    if raw is None or raw == "":
        return DEFAULT_BROKER_UID
    try:
        value = int(raw, 10)
    except ValueError:
        raise CapabilityError("host_broker_configuration_invalid") from None
    if value < 0:
        raise CapabilityError("host_broker_configuration_invalid")
    return value


def verify_peer_uid(connection: socket.socket, expected_uid: int) -> None:
    if not hasattr(socket, "SO_PEERCRED"):
        raise CapabilityError("host_broker_peer_unverified")
    size = struct.calcsize("3i")
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
    except (OSError, struct.error):
        raise CapabilityError("host_broker_peer_unverified") from None
    if uid != expected_uid:
        raise CapabilityError("host_broker_peer_unverified")


def recv_line(connection: socket.socket, maximum: int) -> bytes:
    data = bytearray()
    while len(data) <= maximum:
        chunk = connection.recv(min(8192, maximum + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > maximum:
        raise CapabilityError("host_broker_response_invalid")
    if b"\n" in data:
        line, trailing = bytes(data).split(b"\n", 1)
        if trailing:
            raise CapabilityError("host_broker_response_invalid")
        return line
    if not data:
        raise CapabilityError("host_broker_unavailable")
    return bytes(data)


def safe_identifier(value) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER_RE.fullmatch(value) is not None


def bounded_identifier(value, code):
    if not safe_identifier(value):
        raise CapabilityError(code)
    return value


def sha256_fingerprint(value) -> bool:
    prefix = "sha256:"
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and len(value) == len(prefix) + 64
        and all(char in "0123456789abcdef" for char in value[len(prefix) :])
    )


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapabilityError("host_broker_request_invalid") from None


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise CapabilityError("host_broker_request_invalid")


def safe_error_code(value) -> str:
    if isinstance(value, str) and _ERROR_CODE_RE.fullmatch(value) is not None:
        return value
    return "broker_error"


def validate_receipt(receipt: dict[str, Any], request: dict[str, Any]) -> None:
    keys = {
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
    if (
        set(receipt) != keys
        or receipt.get("protocol_version") != PROTOCOL_VERSION
        or receipt.get("request_id") != request["request_id"]
        or receipt.get("operation") != request["operation"]
        or receipt.get("phase") != request["phase"]
        or receipt.get("status") not in _RECEIPT_STATUSES
        or receipt.get("effect_state") not in _RECEIPT_EFFECT_STATES
        or not isinstance(receipt.get("summary"), dict)
        or not isinstance(receipt.get("recovery"), dict)
        or set(receipt["recovery"]) != {"classification", "token"}
        or type(receipt.get("started_at")) is not int
        or type(receipt.get("completed_at")) is not int
        or receipt["completed_at"] < receipt["started_at"]
    ):
        raise CapabilityError("host_broker_response_invalid")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or _RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise CapabilityError("host_broker_response_invalid")
    recovery = receipt["recovery"]
    token = recovery.get("token")
    if (
        recovery.get("classification") not in _RECOVERY_CLASSIFICATIONS
        or (
            token is not None
            and (
                not isinstance(token, str)
                or len(token) > 160
                or "\x00" in token
            )
        )
    ):
        raise CapabilityError("host_broker_response_invalid")
    error_code = receipt.get("error_code")
    if error_code is not None and (
        not isinstance(error_code, str) or _ERROR_CODE_RE.fullmatch(error_code) is None
    ):
        raise CapabilityError("host_broker_response_invalid")
    for key in ("precondition_fingerprint", "postcondition_fingerprint"):
        value = receipt.get(key)
        if value is not None and not sha256_fingerprint(value):
            raise CapabilityError("host_broker_response_invalid")
    if len(canonical_json(receipt)) > MAX_RESPONSE_BYTES:
        raise CapabilityError("host_broker_response_invalid")


__all__ = [
    "DEFAULT_SOCKET",
    "MAX_PAYLOAD_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "PHASES",
    "PROTOCOL_VERSION",
    "bounded_identifier",
    "canonical_json",
    "expected_uid_from_environment",
    "recv_line",
    "safe_error_code",
    "safe_identifier",
    "sha256_bytes",
    "sha256_fingerprint",
    "thaw_json",
    "validate_receipt",
    "verify_peer_uid",
]
