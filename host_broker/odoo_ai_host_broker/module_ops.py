"""Lifecycle-safe Odoo module maintenance through fixed external processes."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from typing import Any

from .outcome import BrokerOperationError, OperationOutcome
from .policy import BrokerPolicy, ModuleTarget
from .protocol import canonical_sha256

_TARGET_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_RE = re.compile(r"^receipt:v1:[0-9a-f]{32,64}$")
_INSPECT_PREFIX = "ODOO_AI_MODULE_STATE:"
_MAX_OUTPUT_BYTES = 64 * 1024
ModuleRunner = Callable[..., subprocess.CompletedProcess[str]]


def _default_runner(
    argv,
    *,
    timeout,
    input_text=None,
):
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
        env={
            "HOME": "/nonexistent",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "PYTHONNOUSERSITE": "1",
        },
    )


class ModuleMaintenanceOperations:
    """Run one deployment-owned module update outside the Assistant cron worker."""

    def __init__(
        self,
        policy: BrokerPolicy,
        runner: ModuleRunner | None = None,
    ) -> None:
        self.policy = policy
        self.runner = runner or _default_runner

    def preview_update(
        self,
        payload: dict[str, Any],
        *,
        database_fingerprint: str,
    ) -> OperationOutcome:
        target = self._target(payload, database_fingerprint=database_fingerprint)
        summary, fingerprint = self._inspect(target)
        return OperationOutcome(
            summary=summary,
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
            recovery_classification="external_or_unknown",
        )

    def execute_update(
        self,
        payload: dict[str, Any],
        *,
        database_fingerprint: str,
        expected_precondition: str | None,
    ) -> OperationOutcome:
        target = self._target(payload, database_fingerprint=database_fingerprint)
        if (
            not isinstance(expected_precondition, str)
            or _FINGERPRINT_RE.fullmatch(expected_precondition) is None
        ):
            raise BrokerOperationError("broker_precondition_required")
        before_summary, before = self._inspect(target)
        if before != expected_precondition:
            raise BrokerOperationError(
                "broker_precondition_changed",
                status="stale",
                precondition_fingerprint=before,
                recovery_classification="external_or_unknown",
            )
        completed = self._run(
            target,
            self._base_argv(target)
            + [
                f"--update={target.module}",
                "--stop-after-init",
                "--log-level=warn",
                "--logfile=/dev/null",
            ],
            timeout=target.timeout_seconds,
        )
        if completed.returncode != 0:
            raise BrokerOperationError(
                "broker_module_update_failed",
                status="uncertain",
                effect_state="unknown",
                summary={"target": target.target_id, "module": target.module},
                precondition_fingerprint=before,
                recovery_classification="external_or_unknown",
            )
        after_summary, after = self._inspect(target)
        if (
            after_summary["state"] != "installed"
            or not after_summary["source_version"]
            or after_summary["database_version"] != after_summary["source_version"]
        ):
            raise BrokerOperationError(
                "broker_module_update_verify_failed",
                status="uncertain",
                effect_state="unknown",
                summary={"target": target.target_id, "module": target.module},
                precondition_fingerprint=before,
                postcondition_fingerprint=after,
                recovery_classification="external_or_unknown",
            )
        return OperationOutcome(
            effect_state="applied",
            summary={
                **after_summary,
                "previous_database_version": before_summary["database_version"],
            },
            precondition_fingerprint=before,
            postcondition_fingerprint=after,
            recovery_classification="external_or_unknown",
        )

    def verify_update(
        self,
        payload: dict[str, Any],
        *,
        database_fingerprint: str,
    ) -> OperationOutcome:
        target = self._target(
            payload,
            database_fingerprint=database_fingerprint,
            verify=True,
        )
        receipt_id = payload.get("receipt_id")
        expected = payload.get("postcondition_fingerprint")
        if (
            not isinstance(receipt_id, str)
            or _RECEIPT_RE.fullmatch(receipt_id) is None
            or not isinstance(expected, str)
            or _FINGERPRINT_RE.fullmatch(expected) is None
        ):
            raise BrokerOperationError("broker_payload_invalid")
        summary, fingerprint = self._inspect(target)
        verified = (
            fingerprint == expected
            and summary["state"] == "installed"
            and bool(summary["source_version"])
            and summary["database_version"] == summary["source_version"]
        )
        if not verified:
            raise BrokerOperationError(
                "broker_module_update_verify_failed",
                status="error",
                effect_state="unknown",
                summary={"target": target.target_id, "module": target.module},
                postcondition_fingerprint=fingerprint,
                recovery_classification="external_or_unknown",
            )
        return OperationOutcome(
            summary={**summary, "verified": True, "receipt_id": receipt_id},
            precondition_fingerprint=fingerprint,
            postcondition_fingerprint=fingerprint,
        )

    def _target(
        self,
        payload: dict[str, Any],
        *,
        database_fingerprint: str,
        verify: bool = False,
    ) -> ModuleTarget:
        expected = (
            {"target", "receipt_id", "postcondition_fingerprint"}
            if verify
            else {"target"}
        )
        if set(payload) != expected:
            raise BrokerOperationError("broker_payload_invalid")
        target_id = payload.get("target")
        if not isinstance(target_id, str) or _TARGET_RE.fullmatch(target_id) is None:
            raise BrokerOperationError("broker_payload_invalid")
        target = self.policy.module_targets.get(target_id)
        if target is None:
            raise BrokerOperationError("broker_target_denied")
        expected_database = "sha256:" + hashlib.sha256(
            target.database.encode("utf-8")
        ).hexdigest()
        if database_fingerprint != expected_database:
            raise BrokerOperationError("broker_database_denied")
        return target

    def _inspect(self, target: ModuleTarget) -> tuple[dict[str, Any], str]:
        module_literal = json.dumps(target.module)
        script = (
            "import json\n"
            f"module = env['ir.module.module'].search([('name', '=', {module_literal})], limit=1)\n"
            "value = {'module': module.name if module else '', "
            "'state': module.state if module else 'missing', "
            "'database_version': (module.latest_version or None) if module else None, "
            "'source_version': (module.installed_version or None) if module else None}\n"
            f"print({_INSPECT_PREFIX!r} + json.dumps(value, sort_keys=True))\n"
        )
        completed = self._run(
            target,
            [
                target.odoo_python,
                target.odoo_bin,
                "shell",
                *self._base_options(target),
                "--log-level=warn",
                "--logfile=/dev/null",
            ],
            timeout=min(120, target.timeout_seconds),
            input_text=script,
        )
        if completed.returncode != 0:
            raise BrokerOperationError("broker_module_inspection_failed")
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        if len(stdout.encode("utf-8", "replace")) > _MAX_OUTPUT_BYTES:
            raise BrokerOperationError("broker_module_inspection_failed")
        line = next(
            (item for item in reversed(stdout.splitlines()) if item.startswith(_INSPECT_PREFIX)),
            None,
        )
        if line is None:
            raise BrokerOperationError("broker_module_inspection_failed")
        try:
            raw = json.loads(line[len(_INSPECT_PREFIX) :])
        except json.JSONDecodeError as error:
            raise BrokerOperationError("broker_module_inspection_failed") from error
        if (
            not isinstance(raw, dict)
            or set(raw) != {"module", "state", "database_version", "source_version"}
            or raw.get("module") != target.module
            or not isinstance(raw.get("state"), str)
            or any(
                value is not None and not isinstance(value, str)
                for value in (raw.get("database_version"), raw.get("source_version"))
            )
        ):
            raise BrokerOperationError("broker_module_inspection_failed")
        summary = {"target": target.target_id, **raw}
        return summary, canonical_sha256(summary)

    def _run(
        self,
        target: ModuleTarget,
        argv: list[str],
        *,
        timeout: int,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            secured_argv = [
                self.policy.systemd_run_path,
                "--quiet",
                "--wait",
                "--pipe",
                "--collect",
                f"--uid={target.run_as_uid}",
                f"--gid={target.run_as_gid}",
                "--property=UMask=0077",
                "--property=NoNewPrivileges=yes",
                "--property=PrivateTmp=yes",
                "--property=ProtectKernelTunables=yes",
                "--property=ProtectKernelModules=yes",
                "--property=ProtectKernelLogs=yes",
                "--property=ProtectControlGroups=yes",
                "--property=RestrictAddressFamilies=AF_UNIX",
                "--",
                *argv,
            ]
            return self.runner(
                secured_argv,
                timeout=timeout,
                input_text=input_text,
            )
        except subprocess.TimeoutExpired as error:
            raise BrokerOperationError(
                "broker_module_operation_timeout",
                status="uncertain",
                effect_state="unknown",
                recovery_classification="external_or_unknown",
            ) from error
        except (OSError, subprocess.SubprocessError) as error:
            raise BrokerOperationError("broker_module_operation_unavailable") from error

    @staticmethod
    def _base_options(target: ModuleTarget) -> list[str]:
        return [
            f"--config={target.config_path}",
            f"--database={target.database}",
            f"--addons-path={','.join(target.addons_path)}",
            "--no-http",
        ]

    def _base_argv(self, target: ModuleTarget) -> list[str]:
        return [target.odoo_python, target.odoo_bin, *self._base_options(target)]


__all__ = ["ModuleMaintenanceOperations", "ModuleRunner"]
