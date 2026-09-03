"""Finite dispatch and durable replay handling for the local privilege broker."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Callable

from .config_ops import ConfigOperations
from .ledger import ExecutionLedger
from .outcome import BrokerOperationError, OperationOutcome
from .policy import BrokerPolicy
from .protocol import BrokerProtocolError, PROTOCOL_VERSION, canonical_sha256, validate_request
from .service_ops import CommandRunner, ServiceOperations


class BrokerEngine:
    """Dispatch reviewed logical operations; never accepts commands or filesystem paths."""

    def __init__(
        self,
        *,
        policy: BrokerPolicy,
        ledger: ExecutionLedger,
        backups_dir: str | Path,
        runner: CommandRunner | None = None,
    ) -> None:
        self.policy = policy
        self.ledger = ledger
        self.config = ConfigOperations(policy, backups_dir)
        self.services = ServiceOperations(policy, runner)

    def handle(self, *, peer_uid: int, request: dict[str, Any], now: int | None = None):
        current = int(time.time()) if now is None else now
        try:
            validated = validate_request(request, now=current)
        except BrokerProtocolError as error:
            return self._invalid_receipt(request, error.code, current)
        if peer_uid not in self.policy.allowed_peer_uids:
            return self._receipt(validated, OperationOutcome(status="denied", error_code="broker_peer_denied"), current)
        try:
            outcome = self._dispatch(validated)
        except BrokerOperationError as error:
            outcome = error.outcome
        except Exception:
            outcome = OperationOutcome(status="error", error_code="broker_internal_error")
        return self._receipt(validated, outcome, current)

    def _dispatch(self, request: dict[str, Any]) -> OperationOutcome:
        operation, phase, payload = request["operation"], request["phase"], request["payload"]
        if operation == "broker.status" and phase == "preview":
            return OperationOutcome(
                summary={
                    "protocol_version": PROTOCOL_VERSION,
                    "config_targets": sorted(self.policy.config_targets),
                    "service_targets": sorted(self.policy.service_targets),
                    "operation_count": 5,
                }
            )
        if operation == "odoo.config.inspect" and phase == "preview":
            return self.config.inspect(payload)
        if operation == "odoo.config.patch":
            if phase == "preview":
                return self.config.preview_patch(payload)
            if phase == "execute":
                return self._effectful(
                    request,
                    lambda: self.config.execute_patch(
                        payload,
                        request_id=request["request_id"],
                        expected_precondition=request["binding"].get("precondition_fingerprint"),
                    ),
                )
            if phase == "verify":
                return self.config.verify_patch(payload)
        if operation == "host.service.status" and phase == "preview":
            return self.services.status(payload)
        if operation == "host.service.restart":
            if phase == "preview":
                return self.services.preview_restart(payload)
            if phase == "execute":
                return self._effectful(
                    request,
                    lambda: self.services.execute_restart(
                        payload,
                        expected_precondition=request["binding"].get("precondition_fingerprint"),
                    ),
                )
            if phase == "verify":
                return self.services.verify_restart(payload)
        raise BrokerOperationError("broker_operation_not_allowed")

    def _effectful(self, request: dict[str, Any], implementation: Callable[[], OperationOutcome]):
        started_at = int(time.time())
        state, existing = self.ledger.begin(
            request_id=request["request_id"],
            request_hash=canonical_sha256(request),
            operation=request["operation"],
            started_at=started_at,
        )
        if state == "conflict":
            return OperationOutcome(status="denied", error_code="broker_request_replay_mismatch")
        if state == "terminal":
            return _outcome_from_receipt(existing)
        if state == "running":
            return OperationOutcome(
                status="uncertain",
                effect_state="unknown",
                error_code="broker_effect_uncertain",
                recovery_classification="external_or_unknown",
            )
        try:
            outcome = implementation()
        except BrokerOperationError as error:
            outcome = error.outcome
        except Exception:
            outcome = OperationOutcome(
                status="uncertain",
                effect_state="unknown",
                error_code="broker_effect_uncertain",
                recovery_classification="external_or_unknown",
            )
        receipt = self._receipt(request, outcome, started_at)
        try:
            self.ledger.finish(receipt)
        except Exception:
            # The privileged effect may already have happened. A ledger durability failure
            # must never be projected as a proven no-effect error. Leave the stored row in
            # ``running`` so every replay also fails closed as uncertain.
            return OperationOutcome(
                status="uncertain",
                effect_state="unknown",
                precondition_fingerprint=outcome.precondition_fingerprint,
                postcondition_fingerprint=outcome.postcondition_fingerprint,
                recovery_classification=(
                    outcome.recovery_classification
                    if outcome.recovery_classification != "none"
                    else "external_or_unknown"
                ),
                recovery_token=outcome.recovery_token,
                error_code="broker_effect_uncertain",
            )
        return _StoredReceiptOutcome(receipt)

    @staticmethod
    def _receipt_id(request_id: str, phase: str) -> str:
        digest = hashlib.sha256(f"{request_id}|{phase}".encode("ascii")).hexdigest()
        return f"receipt:v1:{digest[:40]}"

    def _receipt(self, request, outcome, started_at):
        if isinstance(outcome, _StoredReceiptOutcome):
            return outcome.receipt
        return {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request["request_id"],
            "receipt_id": self._receipt_id(request["request_id"], request["phase"]),
            "operation": request["operation"],
            "phase": request["phase"],
            "status": outcome.status,
            "effect_state": outcome.effect_state,
            "precondition_fingerprint": outcome.precondition_fingerprint,
            "postcondition_fingerprint": outcome.postcondition_fingerprint,
            "summary": outcome.summary,
            "recovery": {
                "classification": outcome.recovery_classification,
                "token": outcome.recovery_token,
            },
            "error_code": outcome.error_code,
            "started_at": int(started_at),
            "completed_at": int(time.time()),
        }

    def _invalid_receipt(self, request, code, now):
        request_id = request.get("request_id") if isinstance(request, dict) else None
        operation = request.get("operation") if isinstance(request, dict) else None
        phase = request.get("phase") if isinstance(request, dict) else None
        if not isinstance(request_id, str) or re.fullmatch(r"req:v1:[0-9a-f]{32,64}", request_id) is None:
            request_id = "req:v1:" + "0" * 32
        if not isinstance(operation, str) or re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", operation) is None:
            operation = "broker.invalid"
        if phase not in {"preview", "execute", "verify"}:
            phase = "preview"
        safe = {"request_id": request_id, "operation": operation, "phase": phase}
        return self._receipt(safe, OperationOutcome(status="denied", error_code=code), now)


class _StoredReceiptOutcome(OperationOutcome):
    def __init__(self, receipt):
        super().__init__()
        self.receipt = receipt


def _outcome_from_receipt(receipt):
    return _StoredReceiptOutcome(receipt)


__all__ = ["BrokerEngine"]
