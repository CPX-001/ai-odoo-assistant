"""P5.7 explicit conversation-scoped Assistant preferences.

Preferences are Odoo-owned user state. They may shape future turns, but they never
create capability/ACL authority. Autonomy overrides replace the user's durable
selector for one conversation and remain bounded by the existing host policy layers.
"""

from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .chat_policy import _policy_layer
from .conversation_context import _validate_snapshot

_AUTONOMY_PROFILES = {
    "strict": ("always_confirm", "low"),
    "balanced": ("risk_based", "moderate"),
    "autonomous": ("protected_only", "high"),
    "full_access": ("protected_only", "protected"),
}
_RESPONSE_LANGUAGE_SELECTION = [
    ("inherit", "Inherit"),
    ("automatic", "Automatic"),
    ("odoo", "Odoo user language"),
    ("fixed", "Fixed language"),
]
_RESPONSE_LANGUAGE_MODES = frozenset(item[0] for item in _RESPONSE_LANGUAGE_SELECTION)
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{2,8}){0,3}$")


class AssistantConversationPreferences(models.Model):
    _inherit = "odoo.ai.conversation"

    response_language_mode = fields.Selection(
        selection=_RESPONSE_LANGUAGE_SELECTION,
        required=True,
        default="inherit",
        copy=False,
    )
    response_language = fields.Char(size=35, copy=False)

    @api.constrains("response_language_mode", "response_language")
    def _check_response_language_preference(self):
        for record in self:
            _normalize_response_language(
                record.response_language_mode,
                record.response_language or "",
            )

    @api.model
    def response_language_preference(self, conversation_id):
        conversation = self._owned_conversation(conversation_id)
        return {
            "mode": conversation.response_language_mode or "inherit",
            "language": conversation.response_language or "",
        }

    @api.model
    def set_response_language_preference(self, conversation_id, *, mode, language=""):
        conversation = self._owned_conversation(conversation_id)
        normalized_mode, normalized_language = _normalize_response_language(mode, language)
        conversation.write(
            {
                "response_language_mode": normalized_mode,
                "response_language": normalized_language or False,
            }
        )
        return {
            "mode": normalized_mode,
            "language": normalized_language,
        }


class AssistantConversationAutonomyPolicy(models.Model):
    _inherit = "odoo.ai.chat.policy"

    autonomy_override_active = fields.Boolean(required=True, default=False)

    @api.model
    def conversation_autonomy_profile(self, conversation_id):
        self.env["odoo.ai.conversation"]._owned_conversation(conversation_id)
        record = self.search(
            [
                ("user_id", "=", self.env.uid),
                ("conversation_id", "=", conversation_id),
            ],
            limit=1,
        )
        if not record or not record.autonomy_override_active:
            return None
        return _profile_from_policy(record.confirmation_mode, record.max_auto_risk)

    @api.model
    def set_conversation_autonomy_profile(self, conversation_id, profile):
        self.env["odoo.ai.conversation"]._owned_conversation(conversation_id)
        record = self.search(
            [
                ("user_id", "=", self.env.uid),
                ("conversation_id", "=", conversation_id),
            ],
            limit=1,
        )
        if profile in (None, "", "inherit"):
            if record:
                record.write({"autonomy_override_active": False})
            return None
        if profile not in _AUTONOMY_PROFILES:
            raise ValidationError("Invalid Assistant conversation autonomy profile.")
        mode, risk = _AUTONOMY_PROFILES[profile]
        values = {
            "confirmation_mode": mode,
            "max_auto_risk": risk,
            "autonomy_override_active": True,
        }
        if record:
            record.write(values)
        else:
            self.create(
                {
                    **values,
                    "user_id": self.env.uid,
                    "conversation_id": conversation_id,
                }
            )
        return profile

    @api.model
    def policy_layers_for_turn(self, *, conversation_id, message):
        snapshot = super().policy_layers_for_turn(
            conversation_id=conversation_id,
            message=message,
        )
        if not conversation_id:
            return snapshot
        profile = self.conversation_autonomy_profile(conversation_id)
        if profile is None:
            return snapshot
        mode, risk = _AUTONOMY_PROFILES[profile]
        user_layer = snapshot["layers"]["user"]
        # The explicit conversation selector replaces the user's default selector only
        # for this conversation. System/administrator/conversation layers remain in the
        # same host-owned policy snapshot and therefore cannot be bypassed by the model.
        snapshot["layers"]["user"] = _policy_layer(
            mode=mode,
            risk=risk,
            synthetic=user_layer["allow_synthetic_data"],
        )
        return snapshot


class AssistantTurnConversationPreferenceContext(models.Model):
    _inherit = "odoo.ai.turn"

    response_language_mode = fields.Selection(
        selection=_RESPONSE_LANGUAGE_SELECTION,
        required=True,
        readonly=True,
        default="inherit",
        copy=False,
    )
    response_language = fields.Char(readonly=True, size=35, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        captured = []
        for original in vals_list:
            values = dict(original)
            conversation_id = values.get("conversation_id")
            if conversation_id and "response_language_mode" not in values:
                conversation = self.env["odoo.ai.conversation"].browse(conversation_id).exists()
                if not conversation:
                    raise ValidationError("Assistant conversation does not exist")
                values["response_language_mode"] = (
                    conversation.response_language_mode or "inherit"
                )
                values["response_language"] = conversation.response_language or False
            captured.append(values)
        return super().create(captured)

    def write(self, values):
        protected = {"response_language_mode", "response_language"}.intersection(values)
        if protected:
            for record in self:
                for field_name in protected:
                    current = record[field_name] or False
                    incoming = values[field_name] or False
                    if current != incoming:
                        raise ValidationError(
                            "Assistant turn response-language settings are immutable"
                        )
        return super().write(values)

    @api.constrains("response_language_mode", "response_language")
    def _check_turn_response_language_preference(self):
        for record in self:
            _normalize_response_language(
                record.response_language_mode,
                record.response_language or "",
            )

    def _build_conversation_context_snapshot(self):
        self.ensure_one()
        snapshot = super()._build_conversation_context_snapshot()
        settings = dict(snapshot["session_settings"])
        mode = self.response_language_mode or "inherit"
        language = self.response_language or ""
        _normalize_response_language(mode, language)
        settings["response_language_mode"] = mode
        settings["response_language"] = language or False
        snapshot["session_settings"] = settings
        return _validate_snapshot(snapshot)


def _normalize_response_language(mode, language):
    if mode not in _RESPONSE_LANGUAGE_MODES:
        raise ValidationError("Invalid Assistant response-language mode.")
    if not isinstance(language, str):
        raise ValidationError("Invalid Assistant response language.")
    normalized = language.strip()
    if mode == "fixed":
        if not normalized or _LANGUAGE_TAG.fullmatch(normalized) is None:
            raise ValidationError("Invalid Assistant response language.")
    elif normalized:
        raise ValidationError("Response language is only valid in fixed mode.")
    return mode, normalized


def _profile_from_policy(mode, risk):
    if mode == "always_confirm":
        return "strict"
    if mode == "protected_only" and risk == "protected":
        return "full_access"
    if mode == "protected_only":
        return "autonomous"
    return "balanced"
