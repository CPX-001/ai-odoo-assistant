from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..models import reasoning_preferences, user_preferences


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

    def test_reasoning_effort_is_owned_by_current_user(self):
        preferences_a = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        preferences_b = self.env["odoo.ai.user.preference"].with_user(self.user_b)

        self.assertEqual(preferences_a.set_current_reasoning_effort("high"), "high")
        self.assertEqual(preferences_a.current_reasoning_effort(), "high")
        self.assertIsNone(preferences_b.current_reasoning_effort())

        self.assertEqual(preferences_b.set_current_reasoning_effort("low"), "low")
        self.assertEqual(preferences_b.current_reasoning_effort(), "low")
        self.assertEqual(preferences_a.current_reasoning_effort(), "high")

        self.assertIsNone(preferences_a.set_current_reasoning_effort(None))
        self.assertIsNone(preferences_a.current_reasoning_effort())
        self.assertEqual(preferences_b.current_reasoning_effort(), "low")

    def test_response_detail_is_adaptive_user_override_with_admin_default(self):
        preferences_a = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        preferences_b = self.env["odoo.ai.user.preference"].with_user(self.user_b)
        self.env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.default_response_detail", "extensive"
        )

        self.assertEqual(preferences_a.current_response_detail(), "extensive")
        self.assertEqual(preferences_b.current_response_detail(), "extensive")
        self.assertEqual(
            preferences_a.set_current_response_detail("concise"), "concise"
        )
        self.assertEqual(preferences_a.current_response_detail(), "concise")
        self.assertEqual(preferences_b.current_response_detail(), "extensive")

        response = preferences_a.response_detail_preferences()
        self.assertEqual(response["selected_response_detail"], "concise")
        self.assertEqual(response["default_response_detail"], "extensive")
        self.assertEqual(response["effective_response_detail"], "concise")
        self.assertIsNone(preferences_a.set_current_response_detail(None))
        self.assertEqual(preferences_a.current_response_detail(), "extensive")

        rejected = preferences_a.set_response_detail_preference("two_lines")
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "invalid_context")

    def test_reasoning_effort_is_validated_against_effective_model(self):
        catalog = {
            "models": [
                {
                    "model": "gpt-model-a",
                    "display_name": "Model A",
                    "description": "",
                    "family": "gpt-model-a",
                    "variant": None,
                    "family_alias": False,
                    "supported_reasoning_efforts": [{"effort": "high", "description": ""}],
                    "default_reasoning_effort": "high",
                    "is_default": True,
                },
                {
                    "model": "gpt-model-b",
                    "display_name": "Model B",
                    "description": "",
                    "family": "gpt-model-b",
                    "variant": None,
                    "family_alias": False,
                    "supported_reasoning_efforts": [],
                    "default_reasoning_effort": None,
                    "is_default": False,
                },
            ],
            "default_model": "gpt-model-a",
        }
        preferences = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        with patch.object(
            user_preferences,
            "_embedded_model_catalog",
            return_value=catalog,
        ), patch.object(
            reasoning_preferences,
            "_embedded_model_catalog",
            return_value=catalog,
        ):
            accepted = preferences.set_chat_reasoning_effort_preference("high")
            self.assertTrue(accepted["ok"])
            self.assertEqual(accepted["selected_reasoning_effort"], "high")

            rejected = preferences.set_chat_reasoning_effort_preference("max")
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "invalid_context")

            changed = preferences.set_chat_model_preference("gpt-model-b")
            self.assertTrue(changed["ok"])
            self.assertEqual(changed["selected_model"], "gpt-model-b")
            self.assertIsNone(changed["selected_reasoning_effort"])
            self.assertIsNone(preferences.current_reasoning_effort())

    def test_auto_reasoning_is_host_mode_and_requires_routable_provider_levels(self):
        catalog = {
            "models": [
                {
                    "model": "gpt-auto",
                    "display_name": "Auto model",
                    "description": "",
                    "family": "gpt-auto",
                    "variant": None,
                    "family_alias": False,
                    "supported_reasoning_efforts": [
                        {"effort": "low", "description": ""},
                        {"effort": "medium", "description": ""},
                        {"effort": "high", "description": ""},
                    ],
                    "default_reasoning_effort": "medium",
                    "is_default": True,
                },
                {
                    "model": "gpt-limited",
                    "display_name": "Limited model",
                    "description": "",
                    "family": "gpt-limited",
                    "variant": None,
                    "family_alias": False,
                    "supported_reasoning_efforts": [
                        {"effort": "low", "description": ""},
                        {"effort": "medium", "description": ""},
                    ],
                    "default_reasoning_effort": "medium",
                    "is_default": False,
                },
            ],
            "default_model": "gpt-auto",
        }
        preferences = self.env["odoo.ai.user.preference"].with_user(self.user_a)
        with patch.object(
            user_preferences,
            "_embedded_model_catalog",
            return_value=catalog,
        ), patch.object(
            reasoning_preferences,
            "_embedded_model_catalog",
            return_value=catalog,
        ):
            selected = preferences.set_chat_reasoning_effort_preference("auto")
            self.assertTrue(selected["ok"])
            self.assertEqual(selected["selected_reasoning_effort"], "auto")
            self.assertEqual(preferences.current_reasoning_effort(), "auto")

            changed = preferences.set_chat_model_preference("gpt-limited")
            self.assertTrue(changed["ok"])
            self.assertIsNone(changed["selected_reasoning_effort"])
            self.assertIsNone(preferences.current_reasoning_effort())
