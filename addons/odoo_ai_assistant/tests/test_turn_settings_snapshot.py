from datetime import UTC, datetime

from odoo import SUPERUSER_ID, Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


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

    def _screen(self):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": None,
            "selected_ids": [],
            "view_type": "list",
        }

    def _enqueue(self, env, *, request_id, message):
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=self._screen(),
            client_request_id=request_id,
        )
        self.assertTrue(result["ok"])
        return env["odoo.ai.turn"]._owned_turn(result["turn_id"])

    def test_future_preference_changes_do_not_mutate_existing_turn_snapshot(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_reasoning_model("snapshot-model-a")
        preference.set_current_agent_profile("strict")

        turn_a = self._enqueue(
            env,
            request_id="request.settings.snapshot.0001",
            message="Captura la configuración A",
        )
        snapshot_a = turn_a.execution_settings_snapshot()
        self.assertEqual(snapshot_a["format_version"], 1)
        self.assertEqual(snapshot_a["reasoning_model"], "snapshot-model-a")
        self.assertEqual(snapshot_a["autonomy_profile"], "strict")
        self.assertEqual(
            snapshot_a["policy"]["layers"]["user"]["confirmation_mode"],
            "always_confirm",
        )

        preference.set_current_reasoning_model("snapshot-model-b")
        preference.set_current_agent_profile("full_access")
        turn_a.invalidate_recordset()
        self.assertEqual(turn_a.execution_settings_snapshot(), snapshot_a)

        turn_b = self._enqueue(
            env,
            request_id="request.settings.snapshot.0002",
            message="Captura la configuración B",
        )
        snapshot_b = turn_b.execution_settings_snapshot()
        self.assertEqual(snapshot_b["reasoning_model"], "snapshot-model-b")
        self.assertEqual(snapshot_b["autonomy_profile"], "full_access")
        self.assertEqual(
            snapshot_b["policy"]["layers"]["user"]["max_auto_risk"],
            "protected",
        )
        self.assertNotEqual(snapshot_a, snapshot_b)

    def test_captured_settings_fields_are_immutable_after_turn_creation(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        preference.set_current_reasoning_model("snapshot-model-fixed")
        preference.set_current_agent_profile("balanced")
        turn = self._enqueue(
            env,
            request_id="request.settings.snapshot.0003",
            message="Fija esta configuración",
        )
        technical = turn.with_user(SUPERUSER_ID)

        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"reasoning_model": "mutated-model"})
        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"policy_payload": {}})
        with self.assertRaisesRegex(ValidationError, "execution settings are immutable"):
            technical.write({"execution_settings_payload": False})

        technical.write({"error_code": "settings_snapshot_test"})
        self.assertEqual(technical.error_code, "settings_snapshot_test")
        self.assertEqual(
            technical.execution_settings_snapshot()["reasoning_model"],
            "snapshot-model-fixed",
        )
