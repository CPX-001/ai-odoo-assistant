from odoo.tests.common import TransactionCase


class TestAssistantChatPolicy(TransactionCase):
    def _synthetic_authorized(self, message):
        result = self.env["odoo.ai.chat.policy"].policy_layers_for_turn(
            conversation_id=None,
            message=message,
        )
        return result["synthetic_data_authorized"]

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
