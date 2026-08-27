"""Dependency-light checks for Phase 2 terminal failure persistence semantics."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FAILURE = ROOT / "addons/odoo_ai_assistant/runtime/agent/failure.py"
TERMINAL = ROOT / "addons/odoo_ai_assistant/runtime/agent/terminal_failure.py"
MODEL = ROOT / "addons/odoo_ai_assistant/models/turn_failure.py"
MODELS_INIT = ROOT / "addons/odoo_ai_assistant/models/__init__.py"


def _load_modules():
    package_name = "phase2_terminal_contract"
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package

    failure_spec = importlib.util.spec_from_file_location(
        f"{package_name}.failure",
        FAILURE,
    )
    failure = importlib.util.module_from_spec(failure_spec)
    sys.modules[failure_spec.name] = failure
    failure_spec.loader.exec_module(failure)

    terminal_spec = importlib.util.spec_from_file_location(
        f"{package_name}.terminal_failure",
        TERMINAL,
    )
    terminal = importlib.util.module_from_spec(terminal_spec)
    sys.modules[terminal_spec.name] = terminal
    terminal_spec.loader.exec_module(terminal)
    return failure, terminal


failure, terminal = _load_modules()


class _Carrier(RuntimeError):
    def __init__(self, envelope):
        super().__init__(envelope.code)
        self.code = envelope.code
        self.failure = envelope


def _provider_failure(*, effect_state="none", retryability="safe"):
    return failure.FailureEnvelope(
        code="codex_turn_failed",
        category="provider_capacity",
        stage="provider",
        component="codex",
        retryability=retryability,
        effect_state=effect_state,
        user_action="retry",
        safe_summary="El proveedor está temporalmente saturado.",
        safe_details={"http_status": 503, "provider_retryable": True},
        diagnostic_id="diag-p2-terminal-0001",
        provider_code="serverOverloaded",
    )


class TestTerminalFailurePersistenceContract(unittest.TestCase):
    def test_carried_provider_failure_survives_before_write_barrier(self):
        envelope = terminal.terminal_failure_envelope(
            _Carrier(_provider_failure()),
            error_code="codex_turn_failed",
            write_barrier=False,
        )
        self.assertEqual(envelope.category, "provider_capacity")
        self.assertEqual(envelope.component, "codex")
        self.assertEqual(envelope.retryability, "safe")
        self.assertEqual(envelope.effect_state, "none")
        self.assertEqual(envelope.provider_code, "serverOverloaded")
        self.assertEqual(envelope.safe_details["http_status"], 503)
        self.assertEqual(envelope.diagnostic_id, "diag-p2-terminal-0001")

    def test_write_barrier_overrides_provider_retry_hint_and_effect_claim(self):
        envelope = terminal.terminal_failure_envelope(
            _Carrier(_provider_failure()),
            error_code="codex_turn_failed",
            write_barrier=True,
        )
        self.assertEqual(envelope.category, "provider_capacity")
        self.assertEqual(envelope.effect_state, "unknown")
        self.assertEqual(envelope.retryability, "never")
        self.assertEqual(envelope.user_action, "review")
        self.assertEqual(envelope.provider_code, "serverOverloaded")

    def test_queue_recovery_routes_use_authoritative_effect_state(self):
        safe = terminal.terminal_failure_envelope(
            None,
            error_code="worker_lost",
            write_barrier=False,
            diagnostic_id="diag-p2-terminal-0002",
        )
        uncertain = terminal.terminal_failure_envelope(
            None,
            error_code="worker_lost_after_write_barrier",
            write_barrier=True,
            diagnostic_id="diag-p2-terminal-0003",
        )
        self.assertEqual(
            (safe.category, safe.component, safe.effect_state, safe.retryability),
            ("queue_worker", "queue", "none", "safe"),
        )
        self.assertEqual(
            (
                uncertain.category,
                uncertain.component,
                uncertain.effect_state,
                uncertain.retryability,
                uncertain.user_action,
            ),
            ("queue_worker", "queue", "unknown", "never", "review"),
        )

    def test_acl_and_verification_are_not_flattened_to_internal(self):
        denied = terminal.terminal_failure_envelope(
            None,
            error_code="access_denied",
            write_barrier=False,
            diagnostic_id="diag-p2-terminal-0004",
        )
        verify = terminal.terminal_failure_envelope(
            None,
            error_code="capability_verification_failed",
            write_barrier=True,
            diagnostic_id="diag-p2-terminal-0005",
        )
        self.assertEqual(
            (denied.category, denied.user_action, denied.effect_state),
            ("odoo_access", "request_access", "none"),
        )
        self.assertEqual(
            (verify.category, verify.stage, verify.effect_state),
            ("verification", "verification", "unknown"),
        )

    def test_model_overlay_persists_and_projects_only_validated_failure_payloads(self):
        source = MODEL.read_text(encoding="utf-8")
        init_source = MODELS_INIT.read_text(encoding="utf-8")
        self.assertIn("failure_payload = fields.Json(readonly=True)", source)
        self.assertIn('status["failure"] = _browser_failure_payload(', source)
        self.assertIn("parse_failure_envelope(", source)
        self.assertIn("failure_envelope_payload(", source)
        self.assertIn("terminal_failure_envelope(", source)
        self.assertIn("def _cron_run_turn_slot(self):", source)
        self.assertIn("_fail_claimed_turn_with_failure(", source)
        self.assertNotIn("str(error)", source)
        self.assertNotIn("repr(error)", source)
        self.assertIn("from . import turn_failure as turn_failure", init_source)


if __name__ == "__main__":
    unittest.main()
