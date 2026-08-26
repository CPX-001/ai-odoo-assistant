from __future__ import annotations

from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..runtime.account import CodexAccountStatus
from ..services import runtime_account


class _FakeManager:
    def __init__(self, status: CodexAccountStatus):
        self.current = status
        self.started = False
        self.cancelled = False
        self.logged_out = False

    def status(self, *, include_rate_limits=False):
        if include_rate_limits and self.current.state == "authenticated":
            return CodexAccountStatus(
                state="authenticated",
                auth_mode=self.current.auth_mode,
                email=self.current.email,
                plan_type=self.current.plan_type,
                rate_limits=(
                    {
                        "limit_id": "codex",
                        "limit_name": "Codex",
                        "used_percent": 23,
                        "window_duration_mins": 300,
                    },
                ),
            )
        return self.current

    def start_login(self):
        self.started = True
        return self.current

    def cancel_login(self):
        self.cancelled = True
        self.current = CodexAccountStatus(state="not_authenticated")
        return self.current

    def logout(self):
        self.logged_out = True
        self.current = CodexAccountStatus(state="not_authenticated")
        return self.current


@tagged("post_install", "-at_install")
class TestRuntimeAccountGate(TransactionCase):
    def setUp(self):
        super().setUp()
        self.parameters = self.env["ir.config_parameter"]
        self.parameters.set_param(
            "odoo_ai_assistant.codex_connection_enabled",
            "false",
        )

    def test_fresh_database_requires_explicit_connection_even_with_provider_session(self):
        manager = _FakeManager(
            CodexAccountStatus(
                state="authenticated",
                auth_mode="chatgpt",
                email="admin@example.com",
                plan_type="plus",
            )
        )
        with patch.object(runtime_account, "_runtime_manager", return_value=manager):
            payload = runtime_account.runtime_account_payload(self.env)

        self.assertEqual(payload["state"], "not_authenticated")
        self.assertTrue(payload["requires_setup"])
        self.assertIsNone(payload["account"])
        self.assertFalse(manager.started)

    def test_legacy_database_without_activation_parameter_keeps_existing_binding(self):
        self.parameters.set_param(
            "odoo_ai_assistant.codex_connection_enabled",
            False,
        )
        self.assertTrue(runtime_account.database_connection_enabled(self.env))

    def test_connect_marks_database_and_reuses_existing_provider_session(self):
        manager = _FakeManager(
            CodexAccountStatus(
                state="authenticated",
                auth_mode="chatgpt",
                email="admin@example.com",
                plan_type="plus",
            )
        )
        with patch.object(runtime_account, "_runtime_manager", return_value=manager):
            payload = runtime_account.connect_database(self.env)

        self.assertTrue(manager.started)
        self.assertTrue(runtime_account.database_connection_enabled(self.env))
        self.assertEqual(payload["state"], "authenticated")
        self.assertEqual(payload["account"]["email"], "admin@example.com")
        self.assertEqual(payload["account"]["rate_limits"][0]["used_percent"], 23)

    def test_turn_gate_fails_closed_before_database_connection(self):
        manager = _FakeManager(CodexAccountStatus(state="authenticated"))
        with (
            patch.object(runtime_account, "_runtime_manager", return_value=manager),
            self.assertRaises(runtime_account.RuntimeAccountGateError) as caught,
        ):
            runtime_account.require_runtime_authenticated(self.env)

        self.assertEqual(caught.exception.code, "codex_not_connected")
