"""Dependency-light checks for the Phase 2 FailureEnvelope contract."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "addons/odoo_ai_assistant/runtime/agent/failure.py"

spec = importlib.util.spec_from_file_location("phase2_failure_contract", CONTRACT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def valid_payload():
    return {
        "code": "codex_turn_failed",
        "category": "provider_connection",
        "stage": "provider",
        "component": "codex",
        "retryability": "unknown",
        "effect_state": "not_started",
        "user_action": "retry",
        "safe_summary": "  Codex no pudo terminar la petición.  ",
        "safe_details": {"http_status": 503, "attempt": 1},
        "diagnostic_id": "diag-12345678",
        "provider_code": "httpConnectionFailed",
    }


class TestFailureEnvelopeContract(unittest.TestCase):
    def test_valid_payload_round_trips_to_fixed_shape(self):
        envelope = module.parse_failure_envelope(valid_payload())
        self.assertIsInstance(envelope, module.FailureEnvelope)
        self.assertEqual(envelope.safe_summary, "Codex no pudo terminar la petición.")
        self.assertEqual(module.failure_envelope_payload(envelope), {
            **valid_payload(),
            "safe_summary": "Codex no pudo terminar la petición.",
        })

    def test_taxonomies_match_phase2_contract(self):
        self.assertIn("authentication", module.FAILURE_CATEGORIES)
        self.assertIn("capability_execution", module.FAILURE_CATEGORIES)
        self.assertIn("verification", module.FAILURE_CATEGORIES)
        self.assertEqual(
            module.FAILURE_RETRYABILITIES,
            {"never", "safe", "after_change", "unknown"},
        )
        self.assertEqual(
            module.FAILURE_EFFECT_STATES,
            {"none", "not_started", "confirmed", "partial", "unknown"},
        )
        self.assertEqual(
            module.FAILURE_USER_ACTIONS,
            {"retry", "reconnect", "clarify", "request_access", "review", "none"},
        )

    def test_unknown_keys_and_invalid_enums_fail_closed(self):
        extra = valid_payload()
        extra["raw_message"] = "upstream detail"
        bad_values = [
            extra,
            {**valid_payload(), "category": "mystery"},
            {**valid_payload(), "category": []},
            {**valid_payload(), "stage": "thinking"},
            {**valid_payload(), "component": "shell"},
            {**valid_payload(), "retryability": "always"},
            {**valid_payload(), "effect_state": "probably_none"},
            {**valid_payload(), "user_action": "rerun_write"},
            {**valid_payload(), "code": "Bad-Code"},
            {**valid_payload(), "diagnostic_id": "short"},
            {**valid_payload(), "provider_code": "raw provider error!"},
        ]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(module.FailureEnvelopeError):
                    module.parse_failure_envelope(value)

    def test_safe_details_are_bounded_json_data(self):
        bad_values = [
            {**valid_payload(), "safe_details": {"bad-key": "x"}},
            {**valid_payload(), "safe_details": {"value": object()}},
            {**valid_payload(), "safe_details": {"value": float("nan")}},
            {**valid_payload(), "safe_details": {"value": "x" * 1025}},
            {**valid_payload(), "safe_details": {"value": [0] * 33}},
            {**valid_payload(), "safe_details": {"value": "x" * 1024, "other": "y" * 4096}},
        ]
        for value in bad_values:
            with self.subTest(value=repr(value)[:120]):
                with self.assertRaises(module.FailureEnvelopeError):
                    module.parse_failure_envelope(value)

    def test_schema_is_closed_and_lists_routing_enums(self):
        schema = module.failure_envelope_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(valid_payload()))
        self.assertEqual(
            set(schema["properties"]["category"]["enum"]),
            module.FAILURE_CATEGORIES,
        )
        self.assertEqual(
            set(schema["properties"]["effect_state"]["enum"]),
            module.FAILURE_EFFECT_STATES,
        )


if __name__ == "__main__":
    unittest.main()
