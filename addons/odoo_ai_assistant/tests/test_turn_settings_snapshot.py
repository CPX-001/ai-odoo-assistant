from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odoo import SUPERUSER_ID, Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models import embedded_runtime


class TestAssistantTurnSettingsSnapshot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Settings Snapshot User",
                "login": "ai-settings-snapshot-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def _screen(self, *, selected_ids=None):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": None,
            "selected_ids": list(selected_ids or []),
            "view_type": "list",
        }

    def _enqueue(self, env, *, request_id, message, screen=None):
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=screen or self._screen(),
            client_request_id=request_id,
        )
        self.assertTrue(result["ok"])
        return env["odoo.ai.turn"]._owned_turn(result["turn_id"])

    def test_future_preference_changes_do_not_mutate_existing_turn_snapshot(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_reasoning_model("snapshot-model-a")
        preference.set_current_reasoning_effort("high")
        preference.set_current_agent_profile("strict")
        preference.set_current_planning_mode("deliberate")

        turn_a = self._enqueue(
            env,
            request_id="request.settings.snapshot.0001",
            message="Captura la configuración A",
        )
        snapshot_a = turn_a.execution_settings_snapshot()
        self.assertEqual(snapshot_a["format_version"], 3)
        self.assertEqual(snapshot_a["reasoning_model"], "snapshot-model-a")
        self.assertEqual(snapshot_a["reasoning_effort"], "high")
        self.assertEqual(snapshot_a["autonomy_profile"], "strict")
        self.assertEqual(snapshot_a["planning_mode"], "deliberate")
        self.assertEqual(snapshot_a["planning_strategy"]["effective_mode"], "deliberate")
        self.assertTrue(snapshot_a["planning_strategy"]["task_plan_required"])
        self.assertEqual(
            snapshot_a["policy"]["layers"]["user"]["confirmation_mode"],
            "always_confirm",
        )

        preference.set_current_reasoning_model("snapshot-model-b")
        preference.set_current_reasoning_effort("low")
        preference.set_current_agent_profile("full_access")
        preference.set_current_planning_mode("adaptive")
        turn_a.invalidate_recordset()
        self.assertEqual(turn_a.execution_settings_snapshot(), snapshot_a)

        turn_b = self._enqueue(
            env,
            request_id="request.settings.snapshot.0002",
            message="Captura la configuración B",
        )
        snapshot_b = turn_b.execution_settings_snapshot()
        self.assertEqual(snapshot_b["reasoning_model"], "snapshot-model-b")
        self.assertEqual(snapshot_b["reasoning_effort"], "low")
        self.assertEqual(snapshot_b["autonomy_profile"], "full_access")
        self.assertEqual(snapshot_b["planning_mode"], "adaptive")
        self.assertEqual(snapshot_b["planning_strategy"]["effective_mode"], "adaptive")
        self.assertEqual(
            snapshot_b["policy"]["layers"]["user"]["max_auto_risk"],
            "protected",
        )
        self.assertNotEqual(snapshot_a, snapshot_b)

    def test_auto_planning_mode_resolves_from_immutable_structural_inputs(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_planning_mode("auto")
        message = (
            "1. Revisa los datos actuales.\n"
            "2. Contrasta los registros seleccionados.\n"
            "3. Explica las diferencias.\n"
            "4. Verifica la resolución."
        )
        turn = self._enqueue(
            env,
            request_id="request.settings.snapshot.auto.0001",
            message=message,
            screen=self._screen(selected_ids=[1, 2]),
        )
        snapshot = turn.execution_settings_snapshot()

        self.assertEqual(snapshot["planning_mode"], "auto")
        self.assertEqual(snapshot["planning_strategy"]["effective_mode"], "deliberate")
        self.assertGreaterEqual(snapshot["planning_strategy"]["complexity_score"], 4)

        preference.set_current_planning_mode("adaptive")
        turn.invalidate_recordset()
        self.assertEqual(turn.execution_settings_snapshot(), snapshot)

    def test_captured_settings_fields_are_immutable_after_turn_creation(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_reasoning_model("snapshot-model-fixed")
        preference.set_current_reasoning_effort("medium")
        preference.set_current_agent_profile("balanced")
        preference.set_current_planning_mode("adaptive")
        turn = self._enqueue(
            env,
            request_id="request.settings.snapshot.0003",
            message="Fija esta configuración",
        )
        technical = turn.with_user(SUPERUSER_ID)

        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"reasoning_model": "mutated-model"})
        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"reasoning_effort": "max"})
        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"policy_payload": {}})
        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"execution_settings_payload": False})

        technical.write({"error_code": "settings_snapshot_test"})
        self.assertEqual(technical.error_code, "settings_snapshot_test")
        snapshot = technical.execution_settings_snapshot()
        self.assertEqual(snapshot["reasoning_model"], "snapshot-model-fixed")
        self.assertEqual(snapshot["reasoning_effort"], "medium")
        self.assertEqual(snapshot["planning_mode"], "adaptive")

    def test_runtime_codex_settings_use_captured_turn_model_and_effort(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_reasoning_model("snapshot-runtime-model-a")
        preference.set_current_reasoning_effort("xhigh")
        turn = self._enqueue(
            env,
            request_id="request.settings.snapshot.0004",
            message="Usa el modelo y razonamiento capturados",
        )

        preference.set_current_reasoning_model("snapshot-runtime-model-b")
        preference.set_current_reasoning_effort("low")
        turn.invalidate_recordset()
        self.assertEqual(turn.reasoning_model, "snapshot-runtime-model-a")
        self.assertEqual(turn.reasoning_effort, "xhigh")

        detected = SimpleNamespace(
            ready=True,
            executable=Path("/opt/odoo-ai-test/bin/codex"),
        )
        runtime_paths = SimpleNamespace(
            codex_home=Path("/tmp/odoo-ai-test-codex-home"),
        )
        with patch.object(embedded_runtime, "detect_codex", return_value=detected), patch.object(
            embedded_runtime.RuntimePaths,
            "from_odoo",
            return_value=SimpleNamespace(ensure=lambda: runtime_paths),
        ):
            settings = env["odoo.ai.embedded.runtime"]._codex_settings(turn)

        self.assertEqual(settings.model, "snapshot-runtime-model-a")
        self.assertEqual(settings.reasoning_effort, "xhigh")
