"""Provider-backed reasoning-effort preferences and per-turn binding."""

from __future__ import annotations

import re
from dataclasses import replace

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..runtime.agent.model_catalog import CodexModelCatalogError
from .user_preferences import _embedded_model_catalog

_EFFORT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_AUTO_REASONING_EFFORT = "auto"
_AUTO_REQUIRED_EFFORTS = frozenset({"low", "medium", "high"})


class AssistantUserReasoningPreference(models.Model):
    _inherit = "odoo.ai.user.preference"

    reasoning_effort = fields.Char(string="Preferred reasoning effort", size=32)

    @api.constrains("reasoning_effort")
    def _check_reasoning_effort(self):
        for record in self:
            value = (record.reasoning_effort or "").strip()
            if value and not _EFFORT_PATTERN.fullmatch(value):
                raise ValidationError("Invalid Assistant reasoning effort.")

    @api.model
    def current_reasoning_effort(self):
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        value = (preference.reasoning_effort or "").strip()
        return value or None

    @api.model
    def set_current_reasoning_effort(self, effort):
        if effort in (None, ""):
            normalized = False
        elif isinstance(effort, str) and _EFFORT_PATTERN.fullmatch(effort):
            normalized = effort
        else:
            raise ValidationError("Invalid Assistant reasoning effort.")
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        if preference:
            preference.write({"reasoning_effort": normalized})
        else:
            self.create({"user_id": self.env.uid, "reasoning_effort": normalized})
        return normalized or None

    @api.model
    def chat_model_preferences(self):
        response = super().chat_model_preferences()
        if response.get("ok") is not True:
            return response
        selected_effort = self.current_reasoning_effort()
        effective = _effective_model(
            response.get("models"),
            selected_model=response.get("selected_model"),
            default_model=response.get("default_model"),
        )
        if selected_effort == _AUTO_REASONING_EFFORT:
            if _has_reasoning_metadata(effective) and not _supports_auto_reasoning(effective):
                selected_effort = self.set_current_reasoning_effort(None)
        else:
            supported = _supported_efforts(effective)
            if (
                selected_effort is not None
                and _has_reasoning_metadata(effective)
                and selected_effort not in supported
            ):
                selected_effort = self.set_current_reasoning_effort(None)
        return {**response, "selected_reasoning_effort": selected_effort}

    @api.model
    def set_chat_model_preference(self, model):
        response = super().set_chat_model_preference(model)
        if response.get("ok") is not True:
            return response
        selected_effort = self.current_reasoning_effort()
        try:
            catalog = _embedded_model_catalog(self.env)
        except (CodexModelCatalogError, OSError, RuntimeError, ValueError):
            return {**response, "selected_reasoning_effort": selected_effort}
        effective = _effective_model(
            catalog.get("models"),
            selected_model=response.get("selected_model"),
            default_model=catalog.get("default_model"),
        )
        if selected_effort == _AUTO_REASONING_EFFORT:
            if _has_reasoning_metadata(effective) and not _supports_auto_reasoning(effective):
                selected_effort = self.set_current_reasoning_effort(None)
        else:
            supported = _supported_efforts(effective)
            if (
                selected_effort is not None
                and _has_reasoning_metadata(effective)
                and selected_effort not in supported
            ):
                selected_effort = self.set_current_reasoning_effort(None)
        return {**response, "selected_reasoning_effort": selected_effort}

    @api.model
    def set_chat_reasoning_effort_preference(self, effort):
        if not self.env.user._is_internal():
            return _error("access_denied")
        if effort in (None, ""):
            return {
                "ok": True,
                "selected_reasoning_effort": self.set_current_reasoning_effort(None),
            }
        if not isinstance(effort, str) or not _EFFORT_PATTERN.fullmatch(effort):
            return _error("invalid_context")
        try:
            catalog = _embedded_model_catalog(self.env)
        except (CodexModelCatalogError, OSError, RuntimeError, ValueError):
            return _error("engine_unavailable")
        effective = _effective_model(
            catalog.get("models"),
            selected_model=self.current_reasoning_model(),
            default_model=catalog.get("default_model"),
        )
        if effort == _AUTO_REASONING_EFFORT:
            allowed = _supports_auto_reasoning(effective)
        else:
            supported = _supported_efforts(effective)
            allowed = bool(supported) and effort in supported
        if not allowed:
            return _error("invalid_context")
        try:
            selected = self.set_current_reasoning_effort(effort)
        except ValidationError:
            return _error("invalid_context")
        return {"ok": True, "selected_reasoning_effort": selected}


class AssistantTurnReasoningPreference(models.Model):
    _inherit = "odoo.ai.turn"

    reasoning_effort = fields.Char(readonly=True, copy=False, size=32)

    @api.constrains("reasoning_effort")
    def _check_turn_reasoning_effort(self):
        for record in self:
            value = (record.reasoning_effort or "").strip()
            if value and not _EFFORT_PATTERN.fullmatch(value):
                raise ValidationError("Invalid Assistant turn reasoning effort.")


class EmbeddedAssistantRuntimeReasoningPreference(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    def _codex_settings(self, turn):
        settings = super()._codex_settings(turn)
        return replace(settings, reasoning_effort=turn.reasoning_effort or None)


def _effective_model(models, *, selected_model, default_model):
    if not isinstance(models, list):
        return None
    target = selected_model or default_model
    if not isinstance(target, str):
        return None
    return next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("model") == target
        ),
        None,
    )


def _supported_efforts(model):
    if not isinstance(model, dict):
        return ()
    values = model.get("supported_reasoning_efforts")
    if not isinstance(values, list):
        return ()
    result = []
    for item in values:
        effort = item.get("effort") if isinstance(item, dict) else None
        if isinstance(effort, str) and _EFFORT_PATTERN.fullmatch(effort):
            result.append(effort)
    return tuple(result)


def _supports_auto_reasoning(model):
    return _AUTO_REQUIRED_EFFORTS.issubset(set(_supported_efforts(model)))


def _has_reasoning_metadata(model):
    return isinstance(model, dict) and isinstance(
        model.get("supported_reasoning_efforts"),
        list,
    )


def _error(code):
    return {"error": {"code": code}, "ok": False}
