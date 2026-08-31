from odoo import Command
from odoo.tests.common import TransactionCase


class TestAssistantPlanningPreferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "Planning Preference User",
                "login": "planning-preference-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def test_default_and_supported_planning_modes_are_user_scoped(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]

        self.assertEqual(preference.current_planning_mode(), "adaptive")
        self.assertEqual(preference.planning_mode_preferences(), {"ok": True, "mode": "adaptive"})
        for mode in ("deliberate", "adaptive"):
            self.assertEqual(
                preference.set_planning_mode_preference(mode),
                {"ok": True, "mode": mode},
            )
            self.assertEqual(preference.current_planning_mode(), mode)

    def test_legacy_auto_value_normalizes_to_direct_and_cannot_be_reselected(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]
        stored = preference.search([("user_id", "=", self.user.id)], limit=1)
        if not stored:
            stored = preference.create({"user_id": self.user.id, "planning_mode": "auto"})
        else:
            stored.write({"planning_mode": "auto"})

        self.assertEqual(preference.current_planning_mode(), "adaptive")
        self.assertEqual(preference.planning_mode_preferences(), {"ok": True, "mode": "adaptive"})
        self.assertEqual(
            preference.set_planning_mode_preference("auto"),
            {"ok": False, "error": {"code": "invalid_context"}},
        )

    def test_invalid_planning_mode_fails_closed(self):
        env = self.env(user=self.user, su=False)
        preference = env["odoo.ai.user.preference"]

        response = preference.set_planning_mode_preference("unbounded")

        self.assertEqual(response, {"ok": False, "error": {"code": "invalid_context"}})
        self.assertEqual(preference.current_planning_mode(), "adaptive")