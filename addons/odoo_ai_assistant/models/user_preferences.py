"""Per-user Assistant preferences stored under native Odoo ownership rules."""

from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class AssistantUserPreference(models.Model):
    _name = "odoo.ai.user.preference"
    _description = "Odoo AI Assistant User Preference"
    _rec_name = "user_id"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.user,
    )
    reasoning_model = fields.Char(string="Preferred Codex model")

    _sql_constraints = [
        (
            "odoo_ai_user_preference_user_unique",
            "unique(user_id)",
            "Only one AI Assistant preference record is allowed per user.",
        )
    ]

    @api.constrains("reasoning_model")
    def _check_reasoning_model(self):
        for record in self:
            value = (record.reasoning_model or "").strip()
            if value and not _MODEL_PATTERN.fullmatch(value):
                raise ValidationError("Invalid Codex model identifier.")

    @api.model
    def current_reasoning_model(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        value = (preference.reasoning_model or "").strip()
        return value or None

    @api.model
    def set_current_reasoning_model(self, model):
        if model in (None, ""):
            normalized = False
        elif isinstance(model, str) and _MODEL_PATTERN.fullmatch(model):
            normalized = model
        else:
            raise ValidationError("Invalid Codex model identifier.")
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if preference:
            preference.write({"reasoning_model": normalized})
        else:
            self.create({"user_id": self.env.uid, "reasoning_model": normalized})
        return normalized or None
