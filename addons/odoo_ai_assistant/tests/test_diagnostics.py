from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.assistant_diagnostics import SERVICE_URL_PARAM
from ..services import AssistantServiceError


class FakeHealthyClient:
    def health(self):
        return {"status": "ok"}

    def admin_status(self):
        return {
            "readiness": "DEGRADED",
            "components": {
                "assistant_database": {"state": "ok"},
                "migrations": {"state": "ok"},
            },
            "instance": None,
        }


@tagged("post_install", "-at_install")
class TestAssistantDiagnostics(TransactionCase):
    def test_unknown_facts_are_not_invented(self):
        self.env["ir.config_parameter"].set_param(
            SERVICE_URL_PARAM, "http://127.0.0.1:8123"
        )
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(type(diagnostics), "_client", return_value=FakeHealthyClient()):
            values = diagnostics._diagnostic_values()

        self.assertEqual(values["service_state"], "ok")
        self.assertEqual(values["readiness"], "DEGRADED")
        self.assertEqual(values["instance_id"], "Unknown")
        self.assertEqual(values["instance_fingerprint"], "Unknown")

    def test_service_failure_is_sanitized(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(
            type(diagnostics),
            "_client",
            side_effect=AssistantServiceError("service_unavailable"),
        ):
            values = diagnostics._diagnostic_values()

        self.assertEqual(values["service_state"], "error")
        self.assertIn("unavailable", values["message"])
        self.assertNotIn("Traceback", values["message"])
