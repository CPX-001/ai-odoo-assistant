"""Odoo-owned per-turn policy layers for agent autonomy."""

from __future__ import annotations

import re

from odoo import api, fields, models

_MODES = {"always_confirm", "risk_based", "protected_only"}
_RISKS = {"low", "moderate", "high", "protected"}
_PERMISSIVE_MODE = "protected_only"
_PERMISSIVE_RISK = "protected"
_SYSTEM_LAYER = {
    "confirmation_mode": _PERMISSIVE_MODE,
    "max_auto_risk": _PERMISSIVE_RISK,
    "allow_synthetic_data": True,
    "max_tool_calls_per_turn": 32,
    "max_write_steps_per_plan": 12,
    "max_replans": 2,
    "max_consecutive_failures": 3,
}


class AssistantChatPolicy(models.Model):
    _name = "odoo.ai.chat.policy"
    _description = "Odoo AI Assistant Conversation Policy"
    _rec_name = "conversation_id"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.user,
    )
    conversation_id = fields.Char(required=True, index=True, size=36)
    # Legacy fields are retained for upgrade compatibility. Confirmation autonomy is now
    # controlled explicitly by the user's single autonomy profile instead of hidden
    # conversation overrides.
    confirmation_mode = fields.Selection(
        selection=[
            ("always_confirm", "Always confirm"),
            ("risk_based", "Risk based"),
            ("protected_only", "Protected only"),
        ],
        required=True,
        default=_PERMISSIVE_MODE,
    )
    max_auto_risk = fields.Selection(
        selection=[
            ("low", "Low"),
            ("moderate", "Moderate"),
            ("high", "High"),
            ("protected", "Protected"),
        ],
        required=True,
        default=_PERMISSIVE_RISK,
    )
    allow_synthetic_data = fields.Boolean(required=True, default=True)
    synthetic_data_authorized = fields.Boolean(required=True, default=False)

    _sql_constraints = [  # noqa: RUF012 - Odoo model metadata
        (
            "user_conversation_uniq",
            "unique(user_id, conversation_id)",
            "Only one AI policy override is allowed per user and conversation.",
        )
    ]

    @api.model
    def policy_layers_for_turn(self, *, conversation_id, message):
        synthetic_override = _synthetic_override(message)
        record = self.browse()
        if conversation_id:
            record = self.search(
                [
                    ("user_id", "=", self.env.uid),
                    ("conversation_id", "=", conversation_id),
                ],
                limit=1,
            )
            if synthetic_override:
                values = dict(synthetic_override)
                if record:
                    record.write(values)
                else:
                    values.update(
                        {
                            "conversation_id": conversation_id,
                            "user_id": self.env.uid,
                            "confirmation_mode": _PERMISSIVE_MODE,
                            "max_auto_risk": _PERMISSIVE_RISK,
                        }
                    )
                    record = self.create(values)

        conversation = _policy_layer(
            mode=_PERMISSIVE_MODE,
            risk=_PERMISSIVE_RISK,
            synthetic=(record.allow_synthetic_data if record else True),
        )
        explicit_synthetic = _explicit_synthetic_request(message)
        persisted_synthetic = bool(record and record.synthetic_data_authorized)
        synthetic_authorization_override = synthetic_override.get(
            "synthetic_data_authorized"
        )
        if synthetic_authorization_override is True:
            persisted_synthetic = True
        elif synthetic_authorization_override is False:
            explicit_synthetic = False
            persisted_synthetic = False
        return {
            "layers": {
                "system_ceiling": dict(_SYSTEM_LAYER),
                "administrator": self._administrator_layer(),
                "user": self.env["odoo.ai.user.preference"].current_agent_policy(),
                "conversation": conversation,
            },
            "synthetic_data_authorized": explicit_synthetic or persisted_synthetic,
        }

    @api.model
    def _administrator_layer(self):
        # Administrator configuration may still disable synthetic/demo data globally, but
        # it no longer silently lowers a user's visible autonomy selection.
        raw_synthetic = (
            self.env["ir.config_parameter"]._get_param(
                "odoo_ai_assistant.agent_allow_synthetic_data"
            )
            or "True"
        )
        return _policy_layer(
            mode=_PERMISSIVE_MODE,
            risk=_PERMISSIVE_RISK,
            synthetic=str(raw_synthetic).strip().lower() in {"1", "true", "yes"},
        )


def _policy_layer(*, mode, risk, synthetic):
    return {
        "confirmation_mode": mode if mode in _MODES else _PERMISSIVE_MODE,
        "max_auto_risk": risk if risk in _RISKS else _PERMISSIVE_RISK,
        "allow_synthetic_data": bool(synthetic),
        "max_tool_calls_per_turn": 32,
        "max_write_steps_per_plan": 12,
        "max_replans": 2,
        "max_consecutive_failures": 3,
    }


def _synthetic_override(message):
    if not isinstance(message, str):
        return {}
    normalized = " ".join(message.casefold().split())
    if re.search(
        r"\bno (?:uses?|crees?)\b.{0,40}\b"
        r"(?:prueba|demo|demostraci[oó]n|fictici[oa]s?|sint[eé]tic[oa]s?|inventad[oa]s?)\b",
        normalized,
    ):
        return {"allow_synthetic_data": False, "synthetic_data_authorized": False}
    if re.search(
        r"\b(?:puedes|autoriza\w*)\b.{0,50}\b"
        r"(?:prueba|demo|demostraci[oó]n|fictici[oa]s?|sint[eé]tic[oa]s?|inventad[oa]s?)\b",
        normalized,
    ):
        return {"allow_synthetic_data": True, "synthetic_data_authorized": True}
    return {}


def _explicit_synthetic_request(message):
    if not isinstance(message, str):
        return False
    normalized = " ".join(message.casefold().split())
    return bool(
        re.search(
            r"\b(prueba|demo|demostraci[oó]n|fictici[oa]s?|sint[eé]tic[oa]s?|"
            r"inventad[oa]s?)\b",
            normalized,
        )
    )
