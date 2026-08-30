"""User planning-mode preference; authority remains in the Odoo host."""

from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_PLANNING_MODES = frozenset({"adaptive", "deliberate", "auto"})


class AssistantUserPlanningPreference(models.Model):
    _inherit = "odoo.ai.user.preference"

    planning_mode = fields.Selection(
        selection=[
            ("adaptive", "Adaptive"),
            ("deliberate", "Plan"),
            ("auto", "Auto"),
        ],
        string="Assistant planning mode",
        default="adaptive",
    )

    @api.model
    def current_planning_mode(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        value = preference.planning_mode if preference else None
        return value if value in _PLANNING_MODES else "adaptive"

    @api.model
    def set_current_planning_mode(self, mode):
        if mode not in _PLANNING_MODES:
            raise ValidationError("Invalid Assistant planning mode.")
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if preference:
            preference.write({"planning_mode": mode})
        else:
            preference = self.create({"user_id": self.env.uid, "planning_mode": mode})
        return preference.planning_mode

    @api.model
    def planning_mode_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        return {"ok": True, "mode": self.current_planning_mode()}

    @api.model
    def set_planning_mode_preference(self, mode):
        if not self.env.user._is_internal() or mode not in _PLANNING_MODES:
            return _error("invalid_context")
        try:
            selected = self.set_current_planning_mode(mode)
        except ValidationError:
            return _error("invalid_context")
        return {"ok": True, "mode": selected}


def _error(code):
    return {"error": {"code": code}, "ok": False}
