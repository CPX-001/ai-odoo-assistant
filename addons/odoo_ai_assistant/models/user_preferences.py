"""Per-user Assistant preferences stored under native Odoo ownership rules."""

from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services import AssistantServiceError

_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_MAX_MODEL_OPTIONS = 50


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
    agent_confirmation_mode = fields.Selection(
        selection=[
            ("always_confirm", "Always confirm"),
            ("risk_based", "Risk based"),
            ("protected_only", "Protected only"),
        ],
        required=True,
        default="risk_based",
    )
    agent_max_auto_risk = fields.Selection(
        selection=[("low", "Low"), ("moderate", "Moderate"), ("high", "High")],
        required=True,
        default="low",
    )
    agent_allow_synthetic_data = fields.Boolean(required=True, default=True)

    _sql_constraints = [  # noqa: RUF012 - Odoo model metadata
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

    @api.model
    def current_agent_policy(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        return {
            "confirmation_mode": preference.agent_confirmation_mode or "risk_based",
            "max_auto_risk": preference.agent_max_auto_risk or "low",
            "allow_synthetic_data": (
                preference.agent_allow_synthetic_data if preference else True
            ),
            "max_tool_calls_per_turn": 32,
            "max_write_steps_per_plan": 12,
            "max_replans": 2,
            "max_consecutive_failures": 3,
        }


class AssistantBridgeUserPreferences(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def _preferred_reasoning_model(self):
        return self.env["odoo.ai.user.preference"].current_reasoning_model()

    @api.model
    def _client(self):
        return super()._client().bind_reasoning_model(self._preferred_reasoning_model())

    @api.model
    def _chat_client(self):
        return super()._chat_client().bind_reasoning_model(
            self._preferred_reasoning_model()
        )

    @api.model
    def chat_model_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        selected = self._preferred_reasoning_model()
        can_manage = self.env.user.has_group("base.group_system")
        try:
            catalog = _validated_model_catalog(self._chat_client().codex_models())
        except (AssistantServiceError, ValueError):
            fallback_models = (
                [
                    {
                        "model": selected,
                        "display_name": selected,
                        "is_default": False,
                    }
                ]
                if selected
                else []
            )
            return {
                "ok": True,
                "models": fallback_models,
                "default_model": None,
                "selected_model": selected,
                "can_manage_settings": can_manage,
            }

        available = {item["model"] for item in catalog["models"]}
        if selected is not None and selected not in available:
            self.env["odoo.ai.user.preference"].set_current_reasoning_model(None)
            selected = None
        return {
            "ok": True,
            "models": catalog["models"],
            "default_model": catalog["default_model"],
            "selected_model": selected,
            "can_manage_settings": can_manage,
        }

    @api.model
    def set_chat_model_preference(self, model):
        if not self.env.user._is_internal():
            return _error("access_denied")
        if model not in (None, "") and (
            not isinstance(model, str) or not _MODEL_PATTERN.fullmatch(model)
        ):
            return _error("invalid_context")
        normalized = model or None
        if normalized is None:
            return {
                "ok": True,
                "selected_model": self.env[
                    "odoo.ai.user.preference"
                ].set_current_reasoning_model(None),
            }
        try:
            catalog = _validated_model_catalog(self._chat_client().codex_models())
        except (AssistantServiceError, ValueError):
            return _error("service_unavailable")
        available = {item["model"] for item in catalog["models"]}
        if normalized not in available:
            return _error("invalid_context")
        try:
            selected = self.env["odoo.ai.user.preference"].set_current_reasoning_model(
                normalized
            )
        except ValidationError:
            return _error("invalid_context")
        return {
            "ok": True,
            "selected_model": selected,
        }

    @api.model
    def agent_policy_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        policy = self.env["odoo.ai.user.preference"].current_agent_policy()
        return {
            "ok": True,
            "confirmation_mode": policy["confirmation_mode"],
            "max_auto_risk": policy["max_auto_risk"],
        }

    @api.model
    def set_agent_policy_preferences(self, confirmation_mode, max_auto_risk):
        if not self.env.user._is_internal():
            return _error("access_denied")
        if confirmation_mode not in {
            "always_confirm",
            "risk_based",
            "protected_only",
        } or max_auto_risk not in {"low", "moderate", "high"}:
            return _error("invalid_context")
        preference = self.env["odoo.ai.user.preference"].search(
            [("user_id", "=", self.env.uid)],
            limit=1,
        )
        values = {
            "agent_confirmation_mode": confirmation_mode,
            "agent_max_auto_risk": max_auto_risk,
        }
        if preference:
            preference.write(values)
        else:
            values["user_id"] = self.env.uid
            self.env["odoo.ai.user.preference"].create(values)
        return {
            "ok": True,
            "confirmation_mode": confirmation_mode,
            "max_auto_risk": max_auto_risk,
        }


def _validated_model_catalog(payload):
    if not isinstance(payload, dict) or set(payload) != {"models", "default_model"}:
        raise ValueError
    models = payload.get("models")
    default_model = payload.get("default_model")
    if (
        not isinstance(models, list)
        or len(models) > _MAX_MODEL_OPTIONS
        or default_model is not None
        and (not isinstance(default_model, str) or not _MODEL_PATTERN.fullmatch(default_model))
    ):
        raise ValueError
    clean = []
    seen = set()
    for item in models:
        if (
            not isinstance(item, dict)
            or set(item) != {"model", "display_name", "is_default"}
            or not isinstance(item.get("model"), str)
            or not _MODEL_PATTERN.fullmatch(item["model"])
            or item["model"] in seen
            or not isinstance(item.get("display_name"), str)
            or not 1 <= len(item["display_name"]) <= 160
            or not isinstance(item.get("is_default"), bool)
        ):
            raise ValueError
        seen.add(item["model"])
        clean.append(dict(item))
    return {"models": clean, "default_model": default_model}


def _error(code):
    return {"error": {"code": code}, "ok": False}
