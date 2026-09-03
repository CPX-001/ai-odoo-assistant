"""Fixed-argv systemd service operations for the local privilege broker."""

from __future__ import annotations

import re
import subprocess
from typing import Any, Callable

from .outcome import BrokerOperationError, OperationOutcome
from .policy import BrokerPolicy, ServiceTarget
from .protocol import canonical_sha256

_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_RE = re.compile(r"^receipt:v1:[0-9a-f]{32,64}$")
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _default_runner(argv, *, timeout):
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
    )


class ServiceOperations:
    def __init__(self, policy: BrokerPolicy, runner: CommandRunner | None = None) -> None:
        self.policy = policy
        self.runner = runner or _default_runner

    def status(self, payload: dict[str, Any]) -> OperationOutcome:
        target = self._target(payload)
        summary, fingerprint = self._status_fields(target)
        summary["fingerprint"] = fingerprint
        return OperationOutcome(
            summary=summary,
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def preview_restart(self, payload: dict[str, Any]) -> OperationOutcome:
        target = self._target(payload)
        current, fingerprint = self._status_fields(target)
        return OperationOutcome(
            summary={
                "target": target.target_id,
                "active_state": current["active_state"],
                "sub_state": current["sub_state"],
            },
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
            recovery_classification="external_or_unknown",
        )

    def execute_restart(
        self,
        payload: dict[str, Any],
        *,
        expected_precondition: str | None,
    ) -> OperationOutcome:
        target = self._target(payload)
        if not isinstance(expected_precondition, str) or _FINGERPRINT_RE.fullmatch(expected_precondition) is None:
            raise BrokerOperationError("broker_precondition_required")
        _, before = self._status_fields(target)
        if before != expected_precondition:
            raise BrokerOperationError(
                "broker_precondition_changed",
                status="stale",
                precondition_fingerprint=before,
                recovery_classification="external_or_unknown",
            )
        try:
            completed = self.runner(
                [self.policy.systemctl_path, "restart", target.unit],
                timeout=target.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise BrokerOperationError(
                "broker_service_restart_timeout",
                status="uncertain",
                effect_state="unknown",
                summary={"target": target.target_id},
                precondition_fingerprint=before,
                recovery_classification="external_or_unknown",
            ) from error
        if completed.returncode != 0:
            summary, after = self._status_or_unknown(target)
            raise BrokerOperationError(
                "broker_service_restart_failed",
                status="uncertain",
                effect_state="unknown",
                summary=summary,
                precondition_fingerprint=before,
                postcondition_fingerprint=after,
                recovery_classification="external_or_unknown",
            )
        summary, after = self._status_fields(target)
        if summary["active_state"] != "active":
            raise BrokerOperationError(
                "broker_service_restart_unhealthy",
                status="uncertain",
                effect_state="unknown",
                summary={
                    "target": target.target_id,
                    "active_state": summary["active_state"],
                    "sub_state": summary["sub_state"],
                },
                precondition_fingerprint=before,
                postcondition_fingerprint=after,
                recovery_classification="external_or_unknown",
            )
        return OperationOutcome(
            effect_state="applied",
            summary={
                "target": target.target_id,
                "active_state": summary["active_state"],
                "sub_state": summary["sub_state"],
            },
            precondition_fingerprint=before,
            postcondition_fingerprint=after,
            recovery_classification="external_or_unknown",
        )

    def verify_restart(self, payload: dict[str, Any]) -> OperationOutcome:
        target = self._target(payload, verify=True)
        summary, fingerprint = self._status_fields(target)
        if summary["active_state"] != "active":
            raise BrokerOperationError(
                "broker_service_verify_failed",
                status="error",
                effect_state="unknown",
                summary={
                    "target": target.target_id,
                    "active_state": summary["active_state"],
                    "sub_state": summary["sub_state"],
                },
                postcondition_fingerprint=fingerprint,
                recovery_classification="external_or_unknown",
            )
        return OperationOutcome(
            summary={
                "target": target.target_id,
                "active_state": summary["active_state"],
                "sub_state": summary["sub_state"],
                "verified": True,
                "receipt_id": payload["receipt_id"],
            },
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def _target(self, payload: dict[str, Any], *, verify=False) -> ServiceTarget:
        if set(payload) != ({"target", "receipt_id"} if verify else {"target"}):
            raise BrokerOperationError("broker_payload_invalid")
        target_id = payload.get("target")
        if not isinstance(target_id, str) or _TARGET_RE.fullmatch(target_id) is None:
            raise BrokerOperationError("broker_payload_invalid")
        if verify:
            receipt_id = payload.get("receipt_id")
            if not isinstance(receipt_id, str) or _RECEIPT_RE.fullmatch(receipt_id) is None:
                raise BrokerOperationError("broker_payload_invalid")
        target = self.policy.service_targets.get(target_id)
        if target is None:
            raise BrokerOperationError("broker_target_denied")
        return target

    def _status_fields(self, target: ServiceTarget) -> tuple[dict[str, Any], str]:
        argv = [
            self.policy.systemctl_path,
            "show",
            target.unit,
            "--no-page",
            "--property=ActiveState,SubState,UnitFileState,ExecMainStatus,ActiveEnterTimestampMonotonic",
        ]
        try:
            completed = self.runner(argv, timeout=min(15, target.timeout_seconds))
        except subprocess.TimeoutExpired as error:
            raise BrokerOperationError("broker_service_status_timeout") from error
        if completed.returncode != 0:
            raise BrokerOperationError("broker_service_status_failed")
        output = completed.stdout if isinstance(completed.stdout, str) else ""
        if len(output.encode("utf-8", "replace")) > 16 * 1024:
            raise BrokerOperationError("broker_service_status_invalid")
        allowed = {
            "ActiveState",
            "SubState",
            "UnitFileState",
            "ExecMainStatus",
            "ActiveEnterTimestampMonotonic",
        }
        fields = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in allowed:
                value = value.strip()
                if len(value) > 160 or "\x00" in value:
                    raise BrokerOperationError("broker_service_status_invalid")
                fields[key] = value
        if "ActiveState" not in fields or "SubState" not in fields:
            raise BrokerOperationError("broker_service_status_invalid")
        summary = {
            "target": target.target_id,
            "active_state": fields["ActiveState"],
            "sub_state": fields["SubState"],
            "unit_file_state": fields.get("UnitFileState", ""),
            "exec_main_status": fields.get("ExecMainStatus", ""),
            "active_enter_timestamp_monotonic": fields.get("ActiveEnterTimestampMonotonic", ""),
        }
        return summary, canonical_sha256(summary)

    def _status_or_unknown(self, target: ServiceTarget):
        try:
            summary, fingerprint = self._status_fields(target)
            return {
                "target": target.target_id,
                "active_state": summary["active_state"],
                "sub_state": summary["sub_state"],
            }, fingerprint
        except BrokerOperationError:
            return {"target": target.target_id, "active_state": "unknown", "sub_state": "unknown"}, None


__all__ = ["ServiceOperations"]
