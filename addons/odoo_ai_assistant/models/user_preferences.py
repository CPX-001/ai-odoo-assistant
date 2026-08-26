"""Per-user Assistant preferences stored under native Odoo ownership rules."""

from __future__ import annotations

import asyncio
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..runtime import RuntimePaths, detect_codex
from ..runtime.agent.codex import CodexAgentSettings
from ..runtime.agent.model_catalog import CodexModelCatalogError, load_codex_model_catalog

_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_AUTONOMY_PROFILES = {
    "strict": ("always_confirm", "low"),
    "balanced": ("risk_based", "moderate"),
    "autonomous": ("protected_only", "high"),
    "full_access": ("protected_only", "protected"),
}
_LEGACY_MODES = {"always_confirm", "risk_based", "protected_only"}
_LEGACY_RISKS = {"low", "moderate", "high"}


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
    agent_autonomy_profile = fields.Selection(
        selection=[
            ("strict", "Strict"),
            ("balanced", "Balanced"),
            ("autonomous", "Autonomous"),
            ("full_access", "Full access"),
        ],
        string="Assistant autonomy",
    )
    # Legacy stored fields remain for upgrade compatibility only. Runtime policy is
    # derived from the single visible autonomy profile.
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
        selection=[
            ("low", "Low"),
            ("moderate", "Moderate"),
            ("high", "High"),
            ("protected", "Protected"),
        ],
        required=True,
        default="moderate",
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
    def current_agent_profile(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if not preference:
            return "balanced"
        profile = preference.agent_autonomy_profile
        if profile in _AUTONOMY_PROFILES:
            return profile
        return _profile_from_legacy(
            preference.agent_confirmation_mode,
            preference.agent_max_auto_risk,
        )

    @api.model
    def set_current_agent_profile(self, profile):
        if profile not in _AUTONOMY_PROFILES:
            raise ValidationError("Invalid Assistant autonomy profile.")
        mode, risk = _AUTONOMY_PROFILES[profile]
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        values = {
            "agent_autonomy_profile": profile,
            "agent_confirmation_mode": mode,
            "agent_max_auto_risk": risk,
        }
        if preference:
            preference.write(values)
        else:
            values["user_id"] = self.env.uid
            preference = self.create(values)
        return preference.agent_autonomy_profile

    @api.model
    def current_agent_policy(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        profile = self.current_agent_profile()
        mode, risk = _AUTONOMY_PROFILES[profile]
        return {
            "confirmation_mode": mode,
            "max_auto_risk": risk,
            "allow_synthetic_data": (
                preference.agent_allow_synthetic_data if preference else True
            ),
            "max_tool_calls_per_turn": 32,
            "max_write_steps_per_plan": 12,
            "max_replans": 2,
            "max_consecutive_failures": 3,
        }

    @api.model
    def chat_model_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        selected = self.current_reasoning_model()
        can_manage = self.env.user.has_group("base.group_system")
        try:
            catalog = _embedded_model_catalog(self.env)
        except (CodexModelCatalogError, OSError, RuntimeError, ValueError):
            fallback_models = (
                [{"model": selected, "display_name": selected, "is_default": False}]
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
            self.set_current_reasoning_model(None)
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
            return {"ok": True, "selected_model": self.set_current_reasoning_model(None)}
        try:
            catalog = _embedded_model_catalog(self.env)
        except (CodexModelCatalogError, OSError, RuntimeError, ValueError):
            return _error("engine_unavailable")
        if normalized not in {item["model"] for item in catalog["models"]}:
            return _error("invalid_context")
        try:
            selected = self.set_current_reasoning_model(normalized)
        except ValidationError:
            return _error("invalid_context")
        return {"ok": True, "selected_model": selected}

    @api.model
    def agent_autonomy_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        return {"ok": True, "profile": self.current_agent_profile()}

    @api.model
    def set_agent_autonomy_preference(self, profile):
        if not self.env.user._is_internal() or profile not in _AUTONOMY_PROFILES:
            return _error("invalid_context")
        try:
            selected = self.set_current_agent_profile(profile)
        except ValidationError:
            return _error("invalid_context")
        return {"ok": True, "profile": selected}

    @api.model
    def agent_policy_preferences(self):
        """Compatibility response for cached pre-profile frontend assets."""
        if not self.env.user._is_internal():
            return _error("access_denied")
        policy = self.current_agent_policy()
        legacy_risk = policy["max_auto_risk"]
        if legacy_risk == "protected":
            legacy_risk = "high"
        return {
            "ok": True,
            "confirmation_mode": policy["confirmation_mode"],
            "max_auto_risk": legacy_risk,
        }

    @api.model
    def set_agent_policy_preferences(self, confirmation_mode, max_auto_risk):
        """Compatibility write path for cached pre-profile frontend assets."""
        if not self.env.user._is_internal():
            return _error("access_denied")
        if confirmation_mode not in _LEGACY_MODES or max_auto_risk not in _LEGACY_RISKS:
            return _error("invalid_context")
        profile = _profile_from_legacy(confirmation_mode, max_auto_risk)
        try:
            selected = self.set_current_agent_profile(profile)
        except ValidationError:
            return _error("invalid_context")
        mode, risk = _AUTONOMY_PROFILES[selected]
        return {
            "ok": True,
            "confirmation_mode": mode,
            "max_auto_risk": "high" if risk == "protected" else risk,
        }


def _embedded_model_catalog(env):
    configured = env["ir.config_parameter"]._get_param(
        "odoo_ai_assistant.codex_executable"
    ) or None
    status = detect_codex(configured)
    if not status.ready or status.executable is None:
        raise CodexModelCatalogError("codex_runtime_not_found")
    paths = RuntimePaths.from_odoo().ensure()
    settings = CodexAgentSettings(
        executable=status.executable,
        codex_home=paths.codex_home,
        model=None,
    )
    return asyncio.run(load_codex_model_catalog(settings))


def _profile_from_legacy(mode, risk):
    if mode == "always_confirm":
        return "strict"
    if mode == "protected_only" and risk == "protected":
        return "full_access"
    if mode == "protected_only":
        return "autonomous"
    return "balanced"


def _error(code):
    return {"error": {"code": code}, "ok": False}
