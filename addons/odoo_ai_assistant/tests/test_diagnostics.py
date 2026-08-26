from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..models.assistant_diagnostics import SERVICE_URL_PARAM
from ..services import AssistantServiceError


class FakeHealthyClient:
    def health(self):
        return {"status": "ok"}

    def admin_status(self):
        return {"readiness": "DEGRADED", "components": {"assistant_database": {"state": "ok"}, "migrations": {"state": "ok"}, "source": {"state": "pending"}, "logs": {"state": "pending"}, "reasoning_engine": {"state": "pending", "detail": "auth_unavailable", "provider": "codex", "protocol": "app-server-jsonl-v2", "runtime_version": "0.149.0", "model": None}}, "instance": None}

    def diagnostics_matrix(self):
        return {"schema_version": 1, "readiness": "DEGRADED", "checked_at": "2026-08-23T21:00:00+00:00", "config_revision": 3, "entries": [{"key": "service.endpoint", "state": "ok", "reason_code": "service_reachable", "remediation_kind": "none", "summary": "ignored backend summary", "remediation_text": "ignored backend remediation"}, {"key": "reasoning.codex", "state": "degraded", "reason_code": "reasoning_auth_unavailable", "remediation_kind": "authenticate_runtime", "summary": "ignored backend summary", "remediation_text": "ignored backend remediation"}]}

    def source_status(self):
        return {"state": "UNKNOWN", "scan_status": "unknown"}


class FakeUntrustedMatrixClient(FakeHealthyClient):
    def diagnostics_matrix(self):
        return {"schema_version": 1, "readiness": "DEGRADED", "checked_at": "2026-08-23T21:00:00+00:00", "config_revision": 1, "entries": [{"key": "logs.provider", "state": "error", "reason_code": "backend_canary_reason", "remediation_kind": "retry", "summary": "SECRET-CANARY backend supplied text", "remediation_text": "run rm -rf /"}]}


@tagged("post_install", "-at_install")
class TestAssistantDiagnostics(TransactionCase):
    def test_current_component_status_is_rendered_without_legacy_workflows(self):
        self.env["ir.config_parameter"].set_param(SERVICE_URL_PARAM, "http://127.0.0.1:8123")
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(type(diagnostics), "_client", return_value=FakeHealthyClient()):
            values = diagnostics._diagnostic_values()
        self.assertEqual(values["service_state"], "ok")
        self.assertEqual(values["readiness"], "DEGRADED")
        self.assertEqual(values["diagnostics_config_revision"], 3)
        self.assertIn("Codex runtime authentication", values["diagnostic_warnings"])
        self.assertNotIn("ignored backend summary", values["diagnostic_warnings"])
        self.assertEqual(values["reasoning_engine_state"], "pending")
        self.assertEqual(values["reasoning_provider"], "codex")
        self.assertEqual(values["reasoning_runtime_version"], "0.149.0")
        self.assertIn("Authenticate Codex", values["reasoning_setup_message"])
        for retired in ("query_capability_state", "navigation_capability_state", "knowledge_capability_state", "how_to_capability_state", "action_capability_state"):
            self.assertNotIn(retired, values)

    def test_unknown_backend_matrix_code_is_not_rendered_as_trusted_text(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(type(diagnostics), "_client", return_value=FakeUntrustedMatrixClient()):
            values = diagnostics._diagnostic_values()
        self.assertIn("omitted", values["diagnostic_warnings"])
        self.assertNotIn("SECRET-CANARY", values["diagnostic_warnings"])
        self.assertNotIn("rm -rf", values["diagnostic_warnings"])

    def test_service_failure_is_sanitized(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(type(diagnostics), "_client", side_effect=AssistantServiceError("service_unavailable")):
            values = diagnostics._diagnostic_values()
        self.assertEqual(values["service_state"], "error")
        self.assertIn("unavailable", values["message"])
        self.assertNotIn("Traceback", values["message"])
        self.assertEqual(values["diagnostic_errors"], values["message"])

    def test_non_admin_cannot_invoke_diagnostics(self):
        user = self.env["res.users"].create({"name": "Cleanup Non Admin", "login": "cleanup-non-admin", "groups_id": [Command.set([self.env.ref("base.group_user").id])]})
        diagnostics = self.env["odoo.ai.assistant.diagnostics"].with_user(user)
        with self.assertRaises(AccessError):
            diagnostics._require_admin()
        with self.assertRaises(AccessError):
            diagnostics.default_get(["readiness"])
