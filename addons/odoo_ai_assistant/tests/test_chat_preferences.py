from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.chat_preferences import (
    DEFAULT_RECENT_CHAT_LIMIT,
    MAX_RECENT_CHAT_LIMIT,
    MIN_RECENT_CHAT_LIMIT,
    RECENT_CHAT_LIMIT_PARAM,
    _bounded_recent_conversations,
    _recent_chat_limit,
)


class TestChatPreferences(TransactionCase):
    def test_recent_chat_limit_defaults_and_clamps(self):
        parameters = self.env["ir.config_parameter"]
        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, False)
        self.assertEqual(_recent_chat_limit(self.env), DEFAULT_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, 999)
        self.assertEqual(_recent_chat_limit(self.env), MAX_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, 1)
        self.assertEqual(_recent_chat_limit(self.env), MIN_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, "invalid")
        self.assertEqual(_recent_chat_limit(self.env), DEFAULT_RECENT_CHAT_LIMIT)

    def test_recent_conversations_are_sorted_and_bounded(self):
        conversations = [
            {"conversation_id": "old", "updated_at": "2026-08-20T10:00:00Z"},
            {"conversation_id": "new", "updated_at": "2026-08-24T10:00:00Z"},
            {"conversation_id": "mid", "updated_at": "2026-08-22T10:00:00Z"},
        ]

        result = _bounded_recent_conversations(conversations, 2)

        self.assertEqual([item["conversation_id"] for item in result], ["new", "mid"])

    def test_settings_reject_out_of_range_recent_chat_limit(self):
        with self.assertRaises(ValidationError):
            self.env["res.config.settings"].create({"assistant_recent_chat_limit": 4})
