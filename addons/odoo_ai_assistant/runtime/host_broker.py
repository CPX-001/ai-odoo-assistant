"""Bounded Odoo-side client for the optional Phase 10 local host broker."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import stat
import time
from collections.abc import Mapping
from typing import Any

from .capabilities.contracts import CapabilityContext, CapabilityError, JsonValue
from .host_broker_wire import (
    DEFAULT_SOCKET,
    MAX_PAYLOAD_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    PHASES,
    PROTOCOL_VERSION,
    bounded_identifier,
    canonical_json,
    expected_uid_from_environment,
    recv_line,
    safe_error_code,
    safe_identifier,
    sha256_bytes,
    sha256_fingerprint,
    thaw_json,
    validate_receipt,
    verify_peer_uid,
)


class HostBrokerClient:
    """One request/response connection per typed broker operation."""

    def __init__(
        self,
        *,
        socket_path: str | None = None,
        expected_uid: int | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.socket_path = socket_path or os.environ.get(
            "ODOO_AI_ASSISTANT_HOST_BROKER_SOCKET",
            DEFAULT_SOCKET,
        )
        if expected_uid is None:
            expected_uid = expected_uid_from_environment()
        self.expected_uid = expected_uid
        self.timeout_seconds = timeout_seconds
        if (
            not isinstance(self.socket_path, str)
            or not os.path.isabs(self.socket_path)
            or "\x00" in self.socket_path
            or len(self.socket_path) > 1024
            or type(self.expected_uid) is not int
            or self.expected_uid < 0
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0.1 <= float(self.timeout_seconds) <= 600.0
        ):
            raise CapabilityError("host_broker_configuration_invalid")

    def available(self) -> bool:
        try:
            st = os.stat(self.socket_path, follow_symlinks=False)
        except OSError:
            return False
        return stat.S_ISSOCK(st.st_mode)

    def call(
        self,
        context: CapabilityContext,
        *,
        capability: str,
        operation: str,
        phase: str,
        payload: Mapping[str, JsonValue],
        effectful: bool = False,
    ) -> dict[str, Any]:
        if phase not in PHASES or not isinstance(payload, Mapping):
            raise CapabilityError("host_broker_request_invalid")
        mutable_payload = thaw_json(payload)
        encoded_payload = canonical_json(mutable_payload)
        if len(encoded_payload) > MAX_PAYLOAD_BYTES:
            raise CapabilityError("host_broker_request_too_large")

        metadata = context.metadata
        step_id = metadata.get("capability_plan_step_id")
        binding_fingerprint = metadata.get("capability_plan_binding_fingerprint")
        precondition_fingerprint = metadata.get("capability_precondition_fingerprint")
        if effectful and (
            not safe_identifier(step_id)
            or not sha256_fingerprint(binding_fingerprint)
            or not sha256_fingerprint(precondition_fingerprint)
        ):
            step_id, binding_fingerprint, precondition_fingerprint = _binding_from_durable_plan(
                context,
                capability=capability,
                arguments=mutable_payload,
            )

        args_fingerprint = sha256_bytes(encoded_payload)
        now = int(time.time())
        request_id = (
            _stable_request_id(
                context.turn_id,
                step_id,
                binding_fingerprint,
                operation,
                args_fingerprint,
            )
            if effectful
            else f"req:v1:{secrets.token_hex(20)}"
        )
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "operation": operation,
            "phase": phase,
            "issued_at": now,
            "expires_at": now + min(120, max(5, int(self.timeout_seconds) + 5)),
            "binding": {
                "turn_id": bounded_identifier(context.turn_id, "host_broker_request_invalid"),
                "conversation_id": (
                    bounded_identifier(context.conversation_id, "host_broker_request_invalid")
                    if context.conversation_id
                    else None
                ),
                "odoo_uid": int(context.env.uid),
                "database_fingerprint": _database_fingerprint(context),
                "capability": capability,
                "step_id": step_id if effectful else None,
                "args_sha256": args_fingerprint,
                "binding_fingerprint": binding_fingerprint if effectful else None,
                "precondition_fingerprint": precondition_fingerprint if effectful else None,
            },
            "payload": mutable_payload,
        }
        raw_request = canonical_json(request) + b"\n"
        if len(raw_request) > MAX_REQUEST_BYTES:
            raise CapabilityError("host_broker_request_too_large")

        receipt = self._exchange(raw_request, effectful=effectful)
        try:
            validate_receipt(receipt, request)
        except CapabilityError as error:
            if effectful:
                raise _uncertain_transport_error(error.code) from error
            raise
        status = receipt["status"]
        if status == "ok":
            return receipt
        code = receipt.get("error_code")
        if status == "stale":
            raise CapabilityError("capability_plan_precondition_changed")
        if status == "uncertain" or receipt.get("effect_state") == "unknown":
            raise CapabilityError(
                "host_effect_uncertain",
                details={"broker_code": safe_error_code(code)},
            )
        if status == "denied":
            raise CapabilityError(
                "host_broker_denied",
                details={"broker_code": safe_error_code(code)},
            )
        raise CapabilityError(
            "host_broker_operation_failed",
            details={"broker_code": safe_error_code(code)},
        )

    def _exchange(
        self,
        raw_request: bytes,
        *,
        effectful: bool = False,
    ) -> dict[str, Any]:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(float(self.timeout_seconds))
        dispatched = False
        try:
            connection.connect(self.socket_path)
            verify_peer_uid(connection, self.expected_uid)
            # Once sending starts, the broker may have received a complete request even if the
            # client loses the socket before receiving its durable receipt. Effectful callers
            # must therefore fail closed as uncertain rather than as a safe-to-retry outage.
            dispatched = True
            connection.sendall(raw_request)
            raw = recv_line(connection, MAX_RESPONSE_BYTES)
        except CapabilityError as error:
            if effectful and dispatched:
                raise _uncertain_transport_error(error.code) from error
            raise
        except (OSError, TimeoutError) as error:
            if effectful and dispatched:
                raise _uncertain_transport_error("broker_transport_uncertain") from error
            raise CapabilityError("host_broker_unavailable") from None
        finally:
            connection.close()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            if effectful:
                raise _uncertain_transport_error("broker_response_uncertain") from error
            raise CapabilityError("host_broker_response_invalid") from None
        if not isinstance(value, dict):
            if effectful:
                raise _uncertain_transport_error("broker_response_uncertain")
            raise CapabilityError("host_broker_response_invalid")
        return value


def _uncertain_transport_error(code: str) -> CapabilityError:
    return CapabilityError(
        "host_effect_uncertain",
        details={"broker_code": safe_error_code(code)},
    )


def _binding_from_durable_plan(
    context: CapabilityContext,
    *,
    capability: str,
    arguments: Mapping[str, JsonValue],
) -> tuple[str, str, str]:
    """Resolve the exact EffectPlan binding already persisted at the write barrier."""

    try:
        turn = context.env["odoo.ai.turn"].search(
            [
                ("turn_uuid", "=", context.turn_id),
                ("user_id", "=", context.env.uid),
            ],
            limit=1,
        )
        if not turn:
            raise CapabilityError("host_broker_plan_binding_missing")
        turn.check_access("read")
        envelope = turn.capability_plan_payload
    except CapabilityError:
        raise
    # The durable-plan lookup crosses the Odoo ORM/registry boundary. Fail closed
    # for any host-side lookup failure without exposing implementation details.
    except Exception:  # noqa: BLE001
        raise CapabilityError("host_broker_plan_binding_missing") from None

    plan = envelope.get("plan") if isinstance(envelope, dict) else None
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        raise CapabilityError("host_broker_plan_binding_missing")
    expected_arguments = canonical_json(thaw_json(arguments))
    matches = []
    for raw_step in steps:
        if (
            not isinstance(raw_step, dict)
            or raw_step.get("capability") != capability
            or raw_step.get("state") not in {"previewed", "executing"}
        ):
            continue
        try:
            same_arguments = canonical_json(raw_step.get("arguments")) == expected_arguments
        except CapabilityError:
            same_arguments = False
        if same_arguments:
            matches.append(raw_step)
    if len(matches) != 1:
        raise CapabilityError("host_broker_plan_binding_missing")
    step = matches[0]
    step_id = step.get("step_id")
    binding_fingerprint = step.get("binding_fingerprint")
    precondition_fingerprint = step.get("precondition_fingerprint")
    if (
        not safe_identifier(step_id)
        or not sha256_fingerprint(binding_fingerprint)
        or not sha256_fingerprint(precondition_fingerprint)
    ):
        raise CapabilityError("host_broker_plan_binding_missing")
    return step_id, binding_fingerprint, precondition_fingerprint


def _database_fingerprint(context: CapabilityContext) -> str:
    dbname = getattr(getattr(context.env, "cr", None), "dbname", None)
    if not isinstance(dbname, str) or not dbname:
        raise CapabilityError("host_broker_request_invalid")
    return sha256_bytes(dbname.encode("utf-8"))


def _stable_request_id(turn_id, step_id, binding_fingerprint, operation, args_fingerprint):
    body = "|".join(
        [str(turn_id), str(step_id), str(binding_fingerprint), str(operation), str(args_fingerprint)]
    ).encode("utf-8")
    return "req:v1:" + hashlib.sha256(body).hexdigest()[:40]


__all__ = ["HostBrokerClient"]
