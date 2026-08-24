from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssistantUserPreferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "AI Model User A",
                "login": "ai-model-user-a",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "AI Model User B",
                "login": "ai-model-user-b",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )

    def test_reasoning_model_is_owned_by_current_user(self):
        preferences_a = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        preferences_b = self.env["odoo.ai.user.preference"].with_user(self.user_b)

        self.assertEqual(
            preferences_a.set_current_reasoning_model("gpt-5-codex"),
            "gpt-5-codex",
        )
        self.assertEqual(preferences_a.current_reasoning_model(), "gpt-5-codex")
        self.assertIsNone(preferences_b.current_reasoning_model())
        self.assertEqual(preferences_b.search_count([]), 0)

        self.assertEqual(
            preferences_b.set_current_reasoning_model("gpt-fast"),
            "gpt-fast",
        )
        self.assertEqual(preferences_b.current_reasoning_model(), "gpt-fast")
        self.assertEqual(preferences_a.current_reasoning_model(), "gpt-5-codex")

        self.assertIsNone(preferences_a.set_current_reasoning_model(None))
        self.assertIsNone(preferences_a.current_reasoning_model())
        self.assertEqual(preferences_b.current_reasoning_model(), "gpt-fast")
