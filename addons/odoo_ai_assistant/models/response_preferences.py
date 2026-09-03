"""Per-user adaptive answer-detail preferences with an administrator default."""

from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..runtime.agent.response_detail import (
    DEFAULT_RESPONSE_DETAIL,
    RESPONSE_DETAIL_LEVELS,
)

DEFAULT_RESPONSE_DETAIL_PARAM = "odoo_ai_assistant.default_response_detail"


class AssistantUserResponsePreference(models.Model):
    _inherit = "odoo.ai.user.preference"

    response_detail = fields.Selection(
        selection=[
            ("concise", "Concise"),
            ("normal", "Normal"),
            ("extensive", "Extensive"),
        ],
        string="Assistant response detail",
    )

    @api.model
    def default_response_detail(self):
        value = self.env["ir.config_parameter"]._get_param(
            DEFAULT_RESPONSE_DETAIL_PARAM
        )
        return value if value in RESPONSE_DETAIL_LEVELS else DEFAULT_RESPONSE_DETAIL

    @api.model
    def current_response_detail_override(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        value = preference.response_detail if preference else None
        return value if value in RESPONSE_DETAIL_LEVELS else None

    @api.model
    def current_response_detail(self):
        return self.current_response_detail_override() or self.default_response_detail()

    @api.model
    def set_current_response_detail(self, response_detail):
        if response_detail in (None, ""):
            normalized = False
        elif response_detail in RESPONSE_DETAIL_LEVELS:
            normalized = response_detail
        else:
            raise ValidationError("Invalid Assistant response detail.")
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if preference:
            preference.write({"response_detail": normalized})
        else:
            preference = self.create(
                {"user_id": self.env.uid, "response_detail": normalized}
            )
        return preference.response_detail or None

    @api.model
    def response_detail_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        selected = self.current_response_detail_override()
        default = self.default_response_detail()
        return {
            "ok": True,
            "selected_response_detail": selected,
            "default_response_detail": default,
            "effective_response_detail": selected or default,
        }

    @api.model
    def set_response_detail_preference(self, response_detail):
        if not self.env.user._is_internal():
            return _error("access_denied")
        if response_detail not in (None, "", *RESPONSE_DETAIL_LEVELS):
            return _error("invalid_context")
        try:
            selected = self.set_current_response_detail(response_detail)
        except ValidationError:
            return _error("invalid_context")
        default = self.default_response_detail()
        return {
            "ok": True,
            "selected_response_detail": selected,
            "default_response_detail": default,
            "effective_response_detail": selected or default,
        }


def _error(code):
    return {"error": {"code": code}, "ok": False}


__all__ = ["DEFAULT_RESPONSE_DETAIL_PARAM"]
