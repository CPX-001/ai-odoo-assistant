from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..runtime.account import (
    CodexAccountError,
    CodexAccountManager,
    CodexAccountStatus,
    _read_state,
    run_device_login_worker,
)
from ..runtime.agent.auth_probe import isolated_account_usable
from ..runtime.agent.codex import CodexAgentError, CodexAgentSettings, _CodexClient
from ..runtime.paths import RuntimePaths


def _fake_codex(root: Path) -> Path:
    executable = root / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "home = Path(os.environ['CODEX_HOME'])\n"
        "auth = home / 'auth.json'\n"
        "mode_file = home / 'fake-mode'\n"
        "def mode():\n"
        "    return mode_file.read_text().strip() if mode_file.exists() else 'normal'\n"
        "for raw in sys.stdin:\n"
        "    request = json.loads(raw)\n"
        "    method = request.get('method')\n"
        "    if 'id' not in request:\n"
        "        continue\n"
        "    rid = request['id']\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': rid, 'result': {'platformFamily': 'unix', 'platformOs': 'linux', 'userAgent': 'fake-codex/9.9.9'}}), flush=True)\n"
        "    elif method == 'account/read':\n"
        "        if mode() == 'malformed_account':\n"
        "            print(json.dumps({'id': rid, 'result': {'account': 'bad'}}), flush=True)\n"
        "        else:\n"
        "            account = {'type': 'chatgpt', 'email': 'user@example.com', 'planType': 'plus'} if auth.exists() else None\n"
        "            print(json.dumps({'id': rid, 'result': {'account': account, 'requiresOpenaiAuth': True}}), flush=True)\n"
        "    elif method == 'account/rateLimits/read':\n"
        "        print(json.dumps({'id': rid, 'result': {'rateLimitsByLimitId': {'codex': {'limitId': 'codex', 'limitName': 'Codex', 'primary': {'usedPercent': 23, 'windowDurationMins': 300, 'resetsAt': 2000000000}, 'secondary': {'usedPercent': 41, 'windowDurationMins': 10080, 'resetsAt': 2000100000}}}}}), flush=True)\n"
        "    elif method == 'account/login/start':\n"
        "        if mode() == 'exit':\n"
        "            sys.exit(0)\n"
        "        if mode() == 'malformed_start':\n"
        "            print(json.dumps({'id': rid, 'result': {'type': 'chatgptDeviceCode'}}), flush=True)\n"
        "            continue\n"
        "        print(json.dumps({'id': rid, 'result': {'type': 'chatgptDeviceCode', 'loginId': 'login-123', 'verificationUrl': 'https://auth.openai.com/codex/device', 'userCode': 'ABCD-1234'}}), flush=True)\n"
        "        if mode() == 'success':\n"
        "            auth.write_text('{\\\"test\\\":\\\"SECRET-CANARY\\\"}')\n"
        "            print(json.dumps({'method': 'account/login/completed', 'params': {'loginId': 'login-123', 'success': True, 'error': None}}), flush=True)\n"
        "        elif mode() == 'failure':\n"
        "            print(json.dumps({'method': 'account/login/completed', 'params': {'loginId': 'login-123', 'success': False, 'error': 'SECRET-CANARY provider detail'}}), flush=True)\n"
        "    elif method == 'account/login/cancel':\n"
        "        print(json.dumps({'id': rid, 'result': {'status': 'canceled'}}), flush=True)\n"
        "    elif method == 'account/logout':\n"
        "        auth.unlink(missing_ok=True)\n"
        "        print(json.dumps({'id': rid, 'result': {}}), flush=True)\n"
        "    elif method == 'thread/start' and not auth.exists():\n"
        "        print(json.dumps({'id': rid, 'error': {'code': -32000, 'message': 'Not authenticated SECRET-CANARY'}}), flush=True)\n"
        "    else:\n"
        "        print(json.dumps({'id': rid, 'error': {'code': -32601, 'message': 'not found'}}), flush=True)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _paths(root: Path) -> RuntimePaths:
    return RuntimePaths(
        root=root / "assistant",
        codex_home=root / "assistant" / "codex",
        runtime=root / "assistant" / "runtime",
        cache=root / "assistant" / "cache",
        source=root / "assistant" / "source",
    ).ensure()


@tagged("post_install", "-at_install")
class TestEmbeddedCodexAccount(TransactionCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(prefix="odoo-ai-auth-test-")
        self.root = Path(self.temporary.name)
        self.paths = _paths(self.root)
        self.executable = _fake_codex(self.root)

    def tearDown(self):
        self.temporary.cleanup()
        super().tearDown()

    def _manager(self, **overrides):
        return CodexAccountManager(
            executable=self.executable,
            paths=self.paths,
            startup_timeout_seconds=overrides.get("startup_timeout_seconds", 3.0),
            request_timeout_seconds=overrides.get("request_timeout_seconds", 2.0),
            shutdown_timeout_seconds=overrides.get("shutdown_timeout_seconds", 0.5),
            login_timeout_seconds=overrides.get("login_timeout_seconds", 60),
        )

    def _mode(self, value: str):
        (self.paths.codex_home / "fake-mode").write_text(value, encoding="utf-8")

    def _wait_status(self, manager, *, terminal_states, timeout=4.0):
        deadline = time.monotonic() + timeout
        status = manager.status()
        while status.state not in terminal_states and time.monotonic() < deadline:
            time.sleep(0.05)
            status = manager.status()
        return status

    def test_logged_out_state(self):
        status = self._manager().status()
        self.assertEqual(status.state, "not_authenticated")
        self.assertFalse(status.connected)

    def test_legacy_auth_is_recognized_without_reading_it_in_odoo(self):
        auth = self.paths.codex_home / "auth.json"
        auth.write_text('{"legacy":"SECRET-CANARY"}', encoding="utf-8")
        auth.chmod(0o600)

        status = self._manager().status(include_rate_limits=True)

        self.assertEqual(status.state, "authenticated")
        self.assertEqual(status.auth_mode, "chatgpt")
        self.assertEqual(status.email, "user@example.com")
        self.assertEqual(status.plan_type, "plus")
        self.assertEqual(status.rate_limits[0]["limit_id"], "codex")
        self.assertNotIn("SECRET-CANARY", repr(status.browser_payload()))

    def test_device_login_success_persists_codex_owned_auth(self):
        self._mode("success")
        manager = self._manager()
        manager.start_login()
        status = self._wait_status(manager, terminal_states={"authenticated", "authentication_error"})

        self.assertTrue(status.connected)
        self.assertTrue((self.paths.codex_home / "auth.json").exists())
        after_restart = self._manager().status()
        self.assertTrue(after_restart.connected)

    def test_pending_device_login_exposes_only_url_and_code_then_cancels(self):
        self._mode("pending")
        manager = self._manager()
        pending = manager.start_login()

        self.assertEqual(pending.state, "login_pending")
        self.assertEqual(pending.user_code, "ABCD-1234")
        self.assertEqual(pending.verification_url, "https://auth.openai.com/codex/device")
        payload = pending.browser_payload()
        self.assertNotIn("login-123", repr(payload))
        self.assertNotIn("pid", repr(payload))

        cancelled = manager.cancel_login()
        self.assertEqual(cancelled.state, "not_authenticated")
        state = _read_state(manager.state_path)
        self.assertEqual(state["state"], "cancelled")
        self.assertIsNone(state["user_code"])

    def test_failed_notification_is_sanitized(self):
        self._mode("failure")
        manager = self._manager()
        try:
            manager.start_login()
        except CodexAccountError as error:
            self.assertEqual(error.code, "codex_login_failed")
        status = self._wait_status(manager, terminal_states={"authentication_error"})
        self.assertEqual(status.error_code, "codex_login_failed")
        state = _read_state(manager.state_path)
        self.assertNotIn("SECRET-CANARY", repr(state))

    def test_malformed_protocol_and_process_exit_fail_closed(self):
        self._mode("malformed_account")
        status = self._manager().status()
        self.assertEqual(status.state, "authentication_error")
        self.assertEqual(status.error_code, "codex_account_response_invalid")

        self._mode("exit")
        with self.assertRaises(CodexAccountError):
            self._manager().start_login()

    def test_malformed_device_response_is_rejected(self):
        self._mode("malformed_start")
        with self.assertRaises(CodexAccountError) as caught:
            self._manager().start_login()
        self.assertEqual(caught.exception.code, "codex_login_response_invalid")

    def test_worker_timeout_becomes_terminal_without_human_ci_login(self):
        self._mode("pending")
        state_path = self.paths.runtime / "timeout-state.json"
        cancel_path = self.paths.runtime / "timeout.cancel"
        asyncio.run(
            run_device_login_worker(
                executable=self.executable,
                codex_home=self.paths.codex_home,
                state_path=state_path,
                cancel_path=cancel_path,
                attempt_id="timeout-attempt",
                login_timeout_seconds=1,
                startup_timeout_seconds=2.0,
                request_timeout_seconds=1.0,
                shutdown_timeout_seconds=0.5,
            )
        )
        state = _read_state(state_path)
        self.assertEqual(state["state"], "timed_out")
        self.assertEqual(state["error_code"], "codex_login_timeout")

    def test_logout_removes_codex_session(self):
        (self.paths.codex_home / "auth.json").write_text("{}", encoding="utf-8")
        status = self._manager().logout()
        self.assertEqual(status.state, "not_authenticated")
        self.assertFalse((self.paths.codex_home / "auth.json").exists())

    def test_symlinked_auth_runtime_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        auth_runtime = self.paths.runtime / "codex_auth"
        if auth_runtime.exists():
            auth_runtime.rmdir()
        auth_runtime.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(CodexAccountError):
            self._manager()

    def test_managed_legacy_auth_is_usable_through_product_isolation(self):
        auth = self.paths.codex_home / "auth.json"
        auth.write_text("{}", encoding="utf-8")
        auth.chmod(0o600)
        usable = asyncio.run(
            isolated_account_usable(
                CodexAgentSettings(
                    executable=self.executable,
                    codex_home=self.paths.codex_home,
                    startup_timeout_seconds=2.0,
                    shutdown_timeout_seconds=0.5,
                )
            )
        )
        self.assertTrue(usable)

    def test_worker_start_failure_does_not_leave_starting_state(self):
        manager = self._manager()
        with patch(
            "odoo.addons.odoo_ai_assistant.runtime.account.subprocess.Popen",
            side_effect=OSError("SECRET-CANARY"),
        ), self.assertRaises(CodexAccountError) as caught:
            manager.start_login()
        self.assertEqual(caught.exception.code, "codex_login_worker_start_failed")
        state = _read_state(manager.state_path)
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["error_code"], "codex_login_worker_start_failed")
        self.assertNotIn("SECRET-CANARY", repr(state))

    def test_product_turn_without_auth_fails_with_sanitized_code(self):
        async def run():
            client = await _CodexClient.start(
                CodexAgentSettings(
                    executable=self.executable,
                    codex_home=self.paths.codex_home,
                    startup_timeout_seconds=2.0,
                    shutdown_timeout_seconds=0.5,
                )
            )
            async with client:
                with self.assertRaises(CodexAgentError) as caught:
                    await client.request(
                        "thread/start",
                        {
                            "approvalPolicy": "never",
                            "cwd": str(client.cwd),
                            "dynamicTools": [],
                            "environments": [],
                            "ephemeral": True,
                            "runtimeWorkspaceRoots": [],
                            "sandbox": "read-only",
                        },
                        timeout=1.0,
                    )
                self.assertEqual(caught.exception.code, "codex_provider_error")
                self.assertNotIn("SECRET-CANARY", repr(caught.exception))

        asyncio.run(run())

    def test_second_login_attempt_reuses_active_attempt(self):
        self._mode("pending")
        manager = self._manager()
        first = manager.start_login()
        state_before = _read_state(manager.state_path)
        second = self._manager().start_login()
        state_after = _read_state(manager.state_path)
        self.assertEqual(first.user_code, second.user_code)
        self.assertEqual(state_before["attempt_id"], state_after["attempt_id"])
        manager.cancel_login()

    def test_stale_login_after_restart_is_recoverable(self):
        manager = self._manager()
        now = int(time.time())
        manager.state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "attempt_id": "stale-attempt",
                    "state": "pending",
                    "created_at": now - 30,
                    "updated_at": now - 30,
                    "deadline_at": now + 30,
                    "pid": 999999,
                    "login_id": "login-stale",
                    "verification_url": "https://auth.openai.com/codex/device",
                    "user_code": "WXYZ-5678",
                    "error_code": None,
                }
            ),
            encoding="utf-8",
        )
        manager.state_path.chmod(0o600)
        status = manager.status()
        self.assertEqual(status.state, "authentication_error")
        self.assertEqual(status.error_code, "codex_login_interrupted")

    def test_settings_and_diagnostics_follow_connect_disconnect(self):
        self.env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.codex_executable", str(self.executable)
        )
        auth = self.paths.codex_home / "auth.json"
        auth.write_text("{}", encoding="utf-8")
        auth.chmod(0o600)
        settings = self.env["res.config.settings"].create({})
        diagnostics = self.env["odoo.ai.assistant.diagnostics"]
        with patch.object(RuntimePaths, "from_odoo", return_value=self.paths):
            settings.action_assistant_codex_login_start()
            values = settings.get_values()
            self.assertTrue(values["assistant_codex_account_connected"])
            self.assertEqual(values["assistant_codex_plan_type"], "plus")
            before = diagnostics._diagnostic_values()
            self.assertIn("Authenticated", before["codex_account_state"])
            settings.action_assistant_codex_logout()
            after = diagnostics._diagnostic_values()
            self.assertEqual(after["codex_account_state"], "Not connected")

    def test_non_admin_cannot_manage_global_account(self):
        user = self.env["res.users"].create(
            {
                "name": "Auth Non Admin",
                "login": "auth-non-admin",
                "groups_id": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        settings = self.env["res.config.settings"].create({}).with_user(user)
        with self.assertRaises(AccessError):
            settings.action_assistant_codex_login_start()
        with self.assertRaises(AccessError):
            settings.action_assistant_codex_logout()
        with self.assertRaises(AccessError):
            settings.assistant_codex_account_status()

    def test_settings_view_exposes_device_flow_without_secret_fields(self):
        view = self.env.ref(
            "odoo_ai_assistant.res_config_settings_view_form_odoo_ai_assistant_runtime"
        )
        arch = view.arch_db
        self.assertIn("Connect with ChatGPT", arch)
        self.assertIn("Open login page", arch)
        self.assertIn("Disconnect", arch)
        self.assertIn("action_assistant_codex_login_cancel", arch)
        self.assertNotIn("access_token", arch)
        self.assertNotIn("refresh_token", arch)
        self.assertNotIn("auth.json", arch)

    def test_settings_rpc_returns_no_tokens_or_internal_login_state(self):
        fake_status = CodexAccountStatus(
            state="authenticated",
            auth_mode="chatgpt",
            email="safe@example.com",
            plan_type="plus",
        )

        class FakeManager:
            def status(self, *, include_rate_limits=False):
                del include_rate_limits
                return fake_status

        settings = self.env["res.config.settings"]
        with patch.object(type(settings), "_codex_account_manager", return_value=FakeManager()):
            payload = settings.assistant_codex_account_status()
        rendered = json.dumps(payload, sort_keys=True)
        self.assertNotIn("access_token", rendered)
        self.assertNotIn("refresh_token", rendered)
        self.assertNotIn("auth.json", rendered)
        self.assertNotIn("login_id", rendered)
        self.assertEqual(payload["state"], "authenticated")
