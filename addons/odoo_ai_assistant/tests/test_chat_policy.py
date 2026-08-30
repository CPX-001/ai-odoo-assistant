from odoo.tests.common import TransactionCase

from ..models.chat_policy import resolve_capability_policy


class TestAssistantChatPolicy(TransactionCase):
    def _snapshot(self, message="Consulta segura"):
        return self.env["odoo.ai.chat.policy"].policy_layers_for_turn(
            conversation_id=None,
            message=message,
        )

    def _synthetic_authorized(self, message):
        return self._snapshot(message)["synthetic_data_authorized"]

    def test_invented_invoice_data_is_explicitly_authorized(self):
        self.assertTrue(
            self._synthetic_authorized(
                "puedes crear 5 facturas con datos inventados?"
            )
        )

    def test_invented_data_singular_is_explicitly_authorized(self):
        self.assertTrue(
            self._synthetic_authorized("Crea una factura con información inventada")
        )

    def test_explicit_synthetic_negation_wins(self):
        self.assertFalse(
            self._synthetic_authorized("No crees facturas con datos inventados")
        )
        self.assertFalse(
            self._synthetic_authorized("No uses datos sintéticos")
        )

    def test_effective_capability_policy_uses_user_autonomy_once(self):
        preferences = self.env["odoo.ai.user.preference"]
        expectations = {
            "strict": ("always_confirm", "low"),
            "balanced": ("risk_based", "moderate"),
            "autonomous": ("protected_only", "high"),
            "full_access": ("protected_only", "protected"),
        }
        for profile, expected in expectations.items():
            preferences.set_current_agent_profile(profile)
            effective = resolve_capability_policy(self._snapshot())
            self.assertEqual(
                (effective["confirmation_mode"], effective["max_auto_risk"]),
                expected,
            )
            self.assertEqual(effective["max_tool_calls_per_turn"], 32)
            self.assertEqual(effective["max_write_steps_per_plan"], 12)
            self.assertEqual(effective["max_effect_steps_per_plan"], 5)
