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
        return {
            "readiness": "DEGRADED",
            "components": {
                "assistant_database": {"state": "ok"},
                "migrations": {"state": "ok"},
                "reasoning_engine": {
                    "state": "pending",
                    "detail": "auth_unavailable",
                    "provider": "codex",
                    "protocol": "app-server-jsonl-v2",
                    "runtime_version": "0.149.0",
                    "model": None,
                },
            },
            "workflow_capabilities": {
                "query": {"state": "pending", "detail": "reasoning_unavailable"},
                "navigation": {"state": "ok", "detail": "validated_per_turn"},
                "knowledge": {"state": "pending", "detail": "instance_unknown"},
                "how_to": {"state": "pending", "detail": "reasoning_unavailable"},
                "action": {"state": "pending", "detail": "reasoning_unavailable"},
            },
            "instance": None,
        }

    def diagnostics_matrix(self):
        return {
            "schema_version": 1,
            "readiness": "DEGRADED",
            "checked_at": "2026-08-23T21:00:00+00:00",
            "config_revision": 3,
            "entries": [
                {
                    "key": "service.endpoint",
                    "state": "ok",
                    "reason_code": "service_reachable",
                    "remediation_kind": "none",
                    "summary": "ignored backend summary",
                    "remediation_text": "ignored backend remediation",
                },
                {
                    "key": "reasoning.codex",
                    "state": "degraded",
                    "reason_code": "reasoning_auth_unavailable",
                    "remediation_kind": "authenticate_runtime",
                    "summary": "ignored backend summary",
                    "remediation_text": "ignored backend remediation",
                },
            ],
        }

    def source_status(self):
        return {"state": "UNKNOWN", "scan_status": "unknown"}


class FakeM3Client(FakeHealthyClient):
    def source_rescan(self):
        return {
            "state": "DETECTED",
            "scan_id": "12345678-1234-5678-1234-567812345678",
            "fingerprint": "sha256:" + "a" * 64,
            "metrics": {"files_seen": 3, "stale_files": 0},
        }

    def source_test(self):
        return {
            "candidate": {
                "module": "odoo_ai_m3_sale_project",
                "logical_path": "odoo_ai_m3_sale_project/models/sale_order.py",
                "start_line": 9,
                "end_line": 28,
                "fingerprint": "sha256:" + "a" * 64,
            },
            "excerpt": {
                "lines": [
                    {"number": 9, "text": "def action_confirm(self):"},
                    {"number": 12, "text": "if order.client_order_ref != marker:"},
                ]
            },
        }

    def logs_test(self, payload):
        assert payload["terms"] == ["Traceback"]
        return {
            "state": "OPERATIONAL",
            "provider": "file",
            "results": [
                {
                    "provider": "file",
                    "traceback_fingerprint": "sha256:" + "b" * 64,
                    "excerpt": "Traceback",
                }
            ],
        }

    def logs_traceback(self, fingerprint, *, max_bytes):
        assert fingerprint == "sha256:" + "b" * 64
        assert max_bytes == 16_384
        return {
            "provider": "file",
            "traceback_fingerprint": fingerprint,
            "occurrence_count": 1,
            "excerpt": "Traceback (most recent call last):\nValueError: controlled",
        }


class FakeUntrustedMatrixClient(FakeHealthyClient):
    def diagnostics_matrix(self):
        return {
            "schema_version": 1,
            "readiness": "DEGRADED",
            "checked_at": "2026-08-23T21:00:00+00:00",
            "config_revision": 1,
            "entries": [
                {
                    "key": "logs.provider",
                    "state": "error",
                    "reason_code": "backend_canary_reason",
                    "remediation_kind": "retry",
                    "summary": "SECRET-CANARY backend supplied text",
                    "remediation_text": "run rm -rf /",
                }
            ],
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
        self.assertEqual(values["diagnostics_config_revision"], 3)
        self.assertIn("Codex runtime authentication", values["diagnostic_warnings"])
        self.assertNotIn("ignored backend summary", values["diagnostic_warnings"])
        self.assertEqual(values["instance_id"], "Unknown")
        self.assertEqual(values["instance_fingerprint"], "Unknown")
        self.assertEqual(values["reasoning_engine_state"], "pending")
        self.assertEqual(values["reasoning_provider"], "codex")
        self.assertEqual(values["reasoning_runtime_version"], "0.149.0")
        self.assertIn("Authenticate Codex", values["reasoning_setup_message"])
        self.assertEqual(
            values["query_capability_state"],
            "pending - reasoning_unavailable",
        )
        self.assertEqual(
            values["navigation_capability_state"],
            "ok - validated_per_turn",
        )
        self.assertEqual(
            values["knowledge_capability_state"],
            "pending - instance_unknown",
        )
        self.assertEqual(
            values["how_to_capability_state"],
            "pending - reasoning_unavailable",
        )
        self.assertNotIn("CODEX_HOME", values["reasoning_setup_message"])

    def test_unknown_backend_matrix_code_is_not_rendered_as_trusted_text(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(
            type(diagnostics),
            "_client",
            return_value=FakeUntrustedMatrixClient(),
        ):
            values = diagnostics._diagnostic_values()

        self.assertIn("omitted", values["diagnostic_warnings"])
        self.assertNotIn("SECRET-CANARY", values["diagnostic_warnings"])
        self.assertNotIn("rm -rf", values["diagnostic_warnings"])

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
        self.assertEqual(values["diagnostic_errors"], values["message"])

    def test_admin_actions_show_only_bounded_logical_evidence(self):
        diagnostics = self.env["odoo.ai.assistant.diagnostics"].create({})
        with patch.object(type(diagnostics), "_client", return_value=FakeM3Client()):
            diagnostics.action_rescan_source()
            diagnostics.action_test_source()
            diagnostics.action_test_logs()

        self.assertEqual(diagnostics.source_state, "DETECTED")
        self.assertIn("odoo_ai_m3_sale_project/models/sale_order.py", diagnostics.source_result)
        self.assertIn("Lines: 9-28", diagnostics.source_result)
        self.assertIn("ValueError: controlled", diagnostics.log_result)
        self.assertNotIn("shared_secret", diagnostics.source_result)
        self.assertNotIn("/srv/", diagnostics.log_result)

    def test_non_admin_cannot_invoke_diagnostics_actions_or_default_get(self):
        user = self.env["res.users"].create(
            {
                "name": "M7 Non Admin",
                "login": "m7-non-admin",
                "groups_id": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        diagnostics = self.env["odoo.ai.assistant.diagnostics"].with_user(user)

        with self.assertRaises(AccessError):
            diagnostics._require_admin()
        with self.assertRaises(AccessError):
            diagnostics.default_get(["readiness"])
