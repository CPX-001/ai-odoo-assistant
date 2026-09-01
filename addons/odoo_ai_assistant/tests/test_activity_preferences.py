from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssistantActivityPreferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "AI Activity User A",
                "login": "ai-activity-user-a",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "AI Activity User B",
                "login": "ai-activity-user-b",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )

    def test_defaults_are_bounded_presentation_only(self):
        preferences = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        payload = preferences.activity_presentation_preferences()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["detail_level"], "normal")
        self.assertEqual(payload["transient_threshold_ms"], 1200)
        self.assertEqual(payload["batch_page_size"], 5)
        self.assertEqual(payload["expanded_line_count"], 5)
        self.assertEqual(payload["reasoning_summary"], "concise")
        self.assertEqual(payload["limits"]["max_rendered_activity_items"], 100)
        self.assertEqual(payload["limits"]["max_reasoning_summary_chars"], 2000)

    def test_preferences_are_owned_by_current_user(self):
        preferences_a = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        preferences_b = self.env["odoo.ai.user.preference"].with_user(self.user_b)

        changed = preferences_a.set_activity_presentation_preferences(
            {
                "detail_level": "diagnostic",
                "show_technical_names": True,
                "show_step_durations": True,
                "reasoning_summary": "detailed",
                "batch_page_size": 10,
                "expanded_line_count": 8,
            }
        )
        self.assertTrue(changed["ok"])
        self.assertEqual(changed["detail_level"], "diagnostic")
        self.assertTrue(changed["show_technical_names"])
        self.assertEqual(changed["batch_page_size"], 10)
        self.assertEqual(changed["expanded_line_count"], 8)

        untouched = preferences_b.activity_presentation_preferences()
        self.assertEqual(untouched["detail_level"], "normal")
        self.assertFalse(untouched["show_technical_names"])
        self.assertEqual(preferences_b.search_count([]), 0)

    def test_malformed_or_authority_like_keys_fail_closed(self):
        preferences = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        invalid = [
            {"detail_level": "raw"},
            {"transient_threshold_ms": 9000},
            {"batch_page_size": 0},
            {"expanded_line_count": 0},
            {"expanded_line_count": 21},
            {"reasoning_summary": "private"},
            {"allow_writes": True},
        ]
        for values in invalid:
            result = preferences.set_activity_presentation_preferences(values)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "invalid_context")

    def test_legacy_preference_without_line_count_uses_default(self):
        preferences = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        preference = preferences.create(
            {
                "user_id": self.user_a.id,
                "activity_expanded_line_count": False,
            }
        )

        preference.write({"activity_batch_page_size": 7})

        payload = preferences.activity_presentation_preferences()
        self.assertEqual(payload["expanded_line_count"], 5)
        self.assertEqual(payload["batch_page_size"], 7)
