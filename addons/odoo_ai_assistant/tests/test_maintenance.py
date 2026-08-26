from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


class FakeMaintenanceClient:
    def __init__(self):
        self.calls = []

    def maintenance_status(self):
        return {"latest": [{"operation": "readiness_test", "state": "succeeded", "result_code": "readiness_ok", "summary": "UNTRUSTED-BACKEND-TEXT"}], "active_jobs": []}

    def maintenance_readiness_test(self, payload):
        return self._result("readiness_test", "readiness_ok", payload)

    def maintenance_source_rescan(self, payload):
        return self._job("source_rescan", payload)

    def maintenance_source_test(self, payload):
        return self._result("source_test", "source_test_succeeded", payload)

    def maintenance_logs_test(self, payload):
        return self._result("logs_test", "logs_test_succeeded", payload)

    def maintenance_knowledge_reindex(self, payload):
        return self._job("knowledge_reindex", payload)

    def maintenance_reasoning_test(self, payload):
        return self._result("reasoning_test", "reasoning_operational", payload)

    def maintenance_configuration_revalidate(self, payload):
        return self._result("configuration_revalidate", "configuration_valid", payload)

    def _result(self, operation, result_code, payload):
        self.calls.append((operation, payload))
        return {"operation": operation, "state": "succeeded", "result_code": result_code, "checked_at": "2026-08-24T00:00:00Z", "metrics": {}, "summary": "UNTRUSTED-BACKEND-TEXT"}

    def _job(self, operation, payload):
        self.calls.append((operation, payload))
        return {"job_id": "12345678-1234-5678-1234-567812345678", "operation": operation, "state": "queued", "result_code": None, "metrics": {}, "created_at": "2026-08-24T00:00:00Z", "started_at": None, "completed_at": None, "summary": "UNTRUSTED-BACKEND-TEXT"}


@tagged("post_install", "-at_install")
class TestAssistantMaintenance(TransactionCase):
    def test_all_ui_operations_use_server_derived_actor_and_explicit_methods(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"].create({})
        client = FakeMaintenanceClient()
        actions = ("action_maintenance_readiness_test", "action_maintenance_source_rescan", "action_maintenance_source_test", "action_maintenance_logs_test", "action_maintenance_knowledge_reindex", "action_maintenance_reasoning_test", "action_maintenance_configuration_revalidate")
        with patch.object(type(diagnostics), "_client", return_value=client):
            for action in actions:
                getattr(diagnostics, action)()
        self.assertEqual(len(client.calls), 7)
        for _operation, payload in client.calls:
            self.assertEqual(payload["actor"]["odoo_uid"], self.env.uid)
            self.assertEqual(payload["actor"]["odoo_database"], self.env.cr.dbname)
            self.assertEqual(set(payload), {"actor"})
        self.assertNotIn("UNTRUSTED-BACKEND-TEXT", diagnostics.maintenance_last_result)

    def test_status_renderer_ignores_backend_free_text_and_unknown_codes(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        canary = "M7-MAINTENANCE-CANARY"
        values = diagnostics._maintenance_status_values({"latest": [{"operation": "reasoning_test", "state": "succeeded", "result_code": "reasoning_auth_unavailable", "summary": canary}, {"operation": "reasoning_test", "state": "succeeded", "result_code": "backend_says_run_shell", "summary": canary}], "active_jobs": []})
        self.assertIn("Codex authentication", values["maintenance_latest"])
        self.assertIn("omitted", values["maintenance_latest"])
        self.assertNotIn(canary, values["maintenance_latest"])
        self.assertNotIn("run_shell", values["maintenance_latest"])

    def test_non_admin_cannot_run_maintenance(self):
        user = self.env["res.users"].create({"name": "M7 Maintenance Non Admin", "login": "m7-maintenance-non-admin", "groups_id": [Command.set([self.env.ref("base.group_user").id])]})
        diagnostics = self.env["odoo.ai.assistant.diagnostics"].create({}).with_user(user)
        with self.assertRaises(AccessError):
            diagnostics.action_maintenance_reasoning_test()

    def test_view_contains_only_current_explicit_maintenance_buttons(self):
        arch = self.env.ref("odoo_ai_assistant.view_odoo_ai_assistant_diagnostics_maintenance_form").arch_db
        for action in ("action_maintenance_readiness_test", "action_maintenance_source_rescan", "action_maintenance_source_test", "action_maintenance_logs_test", "action_maintenance_knowledge_reindex", "action_maintenance_reasoning_test", "action_maintenance_configuration_revalidate"):
            self.assertIn(action, arch)
        self.assertNotIn("action_maintenance_action_self_test", arch)
        self.assertNotIn("action_maintenance_run", arch)
