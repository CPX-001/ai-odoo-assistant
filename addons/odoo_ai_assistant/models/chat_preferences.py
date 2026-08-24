"""Lightweight Odoo-owned chat history preferences."""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

RECENT_CHAT_LIMIT_PARAM = "odoo_ai_assistant.recent_chat_limit"
DEFAULT_RECENT_CHAT_LIMIT = 15
MIN_RECENT_CHAT_LIMIT = 5
MAX_RECENT_CHAT_LIMIT = 50


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    assistant_recent_chat_limit = fields.Integer(
        string="Recent chats shown",
        default=DEFAULT_RECENT_CHAT_LIMIT,
        config_parameter=RECENT_CHAT_LIMIT_PARAM,
        groups="base.group_system",
        help=(
            "Maximum number of recent conversations rendered in the Assistant history. "
            "Keep this bounded on modest self-hosted servers."
        ),
    )

    @api.constrains("assistant_recent_chat_limit")
    def _check_assistant_recent_chat_limit(self):
        for record in self:
            value = record.assistant_recent_chat_limit
            if not MIN_RECENT_CHAT_LIMIT <= value <= MAX_RECENT_CHAT_LIMIT:
                raise ValidationError(
                    _(
                        "Recent chats shown must be between %(minimum)s and %(maximum)s.",
                        minimum=MIN_RECENT_CHAT_LIMIT,
                        maximum=MAX_RECENT_CHAT_LIMIT,
                    )
                )


def recent_chat_limit(env) -> int:
    raw = env["ir.config_parameter"]._get_param(RECENT_CHAT_LIMIT_PARAM)
    try:
        value = int(raw) if raw not in {None, ""} else DEFAULT_RECENT_CHAT_LIMIT
    except (TypeError, ValueError):
        return DEFAULT_RECENT_CHAT_LIMIT
    return min(max(value, MIN_RECENT_CHAT_LIMIT), MAX_RECENT_CHAT_LIMIT)
