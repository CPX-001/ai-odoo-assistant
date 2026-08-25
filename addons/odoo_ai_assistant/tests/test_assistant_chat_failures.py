from unittest import TestCase

from ..models.assistant_chat_failures import _failure_answer, _failure_chat_result


class _PolicyBridge:
    def _agent_policy_layers(self, conversation_id, message):
        del conversation_id, message
        layer = {
            "confirmation_mode": "risk_based",
            "max_auto_risk": "low",
            "allow_synthetic_data": True,
        }
        return {
            "layers": {
                "system_ceiling": dict(layer),
                "administrator": dict(layer),
                "user": dict(layer),
                "conversation": dict(layer),
            }
        }


class TestAssistantChatFailures(TestCase):
    def test_failure_answers_are_plain_and_hide_internal_codes(self):
        for code in (
            "access_denied",
            "engine_timeout",
            "agent_budget_exceeded",
            "service_unavailable",
            "evidence_unavailable",
        ):
            answer = _failure_answer(code)

            self.assertGreater(len(answer), 20)
            self.assertNotIn("**Diagnóstico.**", answer)
            self.assertNotIn("**Motivo.**", answer)
            self.assertNotIn("**Solución.**", answer)
            self.assertNotIn("ACL", answer)
            self.assertNotIn("App Server", answer)
            self.assertNotIn(code, answer)

    def test_failure_envelope_cannot_be_confirmed_or_executed(self):
        result = _failure_chat_result(
            _PolicyBridge(),
            code="engine_timeout",
            message="Elimina los presupuestos",
            conversation_id=None,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow"], "AGENT")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["plan"]["state"], "failed")
        self.assertEqual(result["plan"]["steps"], [])
        self.assertFalse(result["plan"]["requires_confirmation"])
        self.assertFalse(result["plan"]["metadata"]["needs_write"])
        self.assertEqual(result["plan"]["metadata"]["estimated_blast_radius"], 0)

    def test_context_failure_does_not_tell_user_to_open_a_specific_view(self):
        answer = _failure_answer("invalid_context")

        self.assertIn("No necesitas abrir una pantalla concreta", answer)

    def test_service_failure_does_not_invent_a_root_cause(self):
        answer = _failure_answer("service_unavailable")

        self.assertIn("No sé todavía por qué", answer)
        self.assertIn("no voy a inventarlo", answer)
