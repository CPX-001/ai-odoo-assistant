"""Dependency-light checks for Phase 2 provider failure normalization."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "addons/odoo_ai_assistant/runtime/agent/failure.py"
WRAPPER = ROOT / "addons/odoo_ai_assistant/runtime/agent/provider_failure.py"
HOST_LOOP = ROOT / "addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py"

spec = importlib.util.spec_from_file_location("phase2_failure_normalization_contract", CONTRACT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


@dataclass
class ProviderFacts:
    category: str | None = None
    http_status_code: int | None = None
    upstream_code: str | None = None


class ProviderError(RuntimeError):
    def __init__(
        self,
        code,
        *,
        provider_failure=None,
        provider_retryable=False,
        raw_message=None,
    ):
        super().__init__(raw_message or code)
        self.code = code
        self.provider_failure = provider_failure
        self.provider_retryable = provider_retryable
        self.raw_message = raw_message


class TestProviderFailureNormalization(unittest.TestCase):
    def normalize(self, error, *, effect_state="none"):
        return module.normalize_provider_failure(
            error,
            component="codex",
            effect_state=effect_state,
            diagnostic_id="diag-p2-000001",
        )

    def test_authentication_and_capacity_routes_are_distinct(self):
        unauthorized = self.normalize(
            ProviderError(
                "codex_turn_failed",
                provider_failure=ProviderFacts(category="unauthorized"),
            )
        )
        self.assertEqual(
            (
                unauthorized.category,
                unauthorized.retryability,
                unauthorized.user_action,
                unauthorized.effect_state,
                unauthorized.provider_code,
            ),
            ("authentication", "after_change", "reconnect", "none", "unauthorized"),
        )

        usage = self.normalize(
            ProviderError(
                "codex_turn_failed",
                provider_failure=ProviderFacts(category="usageLimitExceeded"),
            )
        )
        self.assertEqual(usage.category, "provider_capacity")
        self.assertEqual(usage.retryability, "after_change")
        self.assertEqual(usage.user_action, "retry")

    def test_overload_is_safe_only_with_explicit_provider_fact_and_safe_effect_state(self):
        safe = self.normalize(
            ProviderError(
                "codex_turn_failed",
                provider_failure=ProviderFacts(category="serverOverloaded"),
                provider_retryable=True,
            )
        )
        uncertain = self.normalize(
            ProviderError(
                "codex_turn_failed",
                provider_failure=ProviderFacts(category="serverOverloaded"),
                provider_retryable=True,
            ),
            effect_state="unknown",
        )
        self.assertEqual(safe.retryability, "safe")
        self.assertTrue(safe.safe_details["provider_retryable"])
        self.assertEqual(uncertain.retryability, "unknown")
        self.assertEqual(uncertain.effect_state, "unknown")

    def test_transport_facts_survive_without_raw_provider_text(self):
        error = ProviderError(
            "codex_turn_failed",
            provider_failure=ProviderFacts(
                category="httpConnectionFailed",
                http_status_code=503,
                upstream_code="upstream_transport",
            ),
            raw_message="secret upstream body must not survive",
        )
        envelope = self.normalize(error)
        payload = module.failure_envelope_payload(envelope)
        self.assertEqual(envelope.category, "provider_connection")
        self.assertEqual(envelope.retryability, "unknown")
        self.assertEqual(envelope.safe_details["http_status"], 503)
        self.assertEqual(envelope.safe_details["upstream_code"], "upstream_transport")
        self.assertNotIn("secret", repr(payload))
        self.assertNotIn("raw_message", payload)

    def test_schema_and_plain_timeout_failures_get_specific_product_categories(self):
        schema = self.normalize(
            ProviderError(
                "codex_output_schema_invalid",
                provider_failure=ProviderFacts(
                    category="other",
                    http_status_code=400,
                    upstream_code="invalid_json_schema",
                ),
            )
        )
        self.assertEqual(schema.category, "provider_output")
        self.assertEqual(schema.retryability, "never")
        self.assertEqual(schema.user_action, "review")
        self.assertEqual(schema.provider_code, "invalid_json_schema")

        timeout = self.normalize(ProviderError("codex_read_timeout"))
        self.assertEqual(timeout.category, "provider_connection")
        self.assertEqual(timeout.user_action, "retry")
        self.assertEqual(timeout.effect_state, "none")

    def test_unknown_provider_failure_falls_back_without_inventing_specificity(self):
        envelope = self.normalize(ProviderError("codex_new_future_failure"))
        self.assertEqual(envelope.code, "codex_new_future_failure")
        self.assertEqual(envelope.category, "internal")
        self.assertEqual(envelope.retryability, "unknown")
        self.assertEqual(envelope.user_action, "review")
        self.assertIsNone(envelope.provider_code)

    def test_invalid_boundary_facts_fail_closed(self):
        with self.assertRaises(module.FailureEnvelopeError):
            module.normalize_provider_failure(
                ProviderError("codex_turn_failed"),
                component="shell",
                effect_state="none",
                diagnostic_id="diag-p2-000001",
            )
        with self.assertRaises(module.FailureEnvelopeError):
            module.normalize_provider_failure(
                ProviderError("codex_turn_failed"),
                component="codex",
                effect_state="probably_none",
                diagnostic_id="diag-p2-000001",
            )

    def test_host_loop_wraps_only_the_pre_effect_provider_decision_boundary(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        host = HOST_LOOP.read_text(encoding="utf-8")
        self.assertIn("class ProviderFailureError(AgentTurnError):", wrapper)
        self.assertIn("except NextDecisionValidationError:", wrapper)
        self.assertIn("failure = normalize_provider_failure(", wrapper)
        self.assertIn("except Exception as error:", wrapper)
        self.assertIn("FailureNormalizingDecisionEngine(", host)
        self.assertIn('component="codex"', host)
        self.assertIn('effect_state="none"', host)
        self.assertLess(
            host.index("FailureNormalizingDecisionEngine("),
            host.index("service = AgentTurnService("),
        )
        self.assertLess(
            host.index("service = AgentTurnService("),
            host.index("prepared = asyncio.run(plans.prepare(result.plan))"),
        )


if __name__ == "__main__":
    unittest.main()
