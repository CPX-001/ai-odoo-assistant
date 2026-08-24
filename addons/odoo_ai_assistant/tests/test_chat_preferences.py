from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.chat_preferences import (
    DEFAULT_RECENT_CHAT_LIMIT,
    MAX_RECENT_CHAT_LIMIT,
    MIN_RECENT_CHAT_LIMIT,
    RECENT_CHAT_LIMIT_PARAM,
    recent_chat_limit,
)


class TestChatPreferences(TransactionCase):
    def test_recent_chat_limit_defaults_and_clamps(self):
        parameters = self.env["ir.config_parameter"]
        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, False)
        self.assertEqual(recent_chat_limit(self.env), DEFAULT_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, 999)
        self.assertEqual(recent_chat_limit(self.env), MAX_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, 1)
        self.assertEqual(recent_chat_limit(self.env), MIN_RECENT_CHAT_LIMIT)

        parameters.set_param(RECENT_CHAT_LIMIT_PARAM, "invalid")
        self.assertEqual(recent_chat_limit(self.env), DEFAULT_RECENT_CHAT_LIMIT)

    def test_settings_reject_out_of_range_recent_chat_limit(self):
        with self.assertRaises(ValidationError):
            self.env["res.config.settings"].create({"assistant_recent_chat_limit": 4})
