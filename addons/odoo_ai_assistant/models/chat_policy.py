"""Odoo-owned policy layers and per-conversation restrictions for agent autonomy."""

from __future__ import annotations

import re

from odoo import api, fields, models

_MODES = {"always_confirm", "risk_based", "protected_only"}
_RISKS = {"low", "moderate", "high"}
_SYSTEM_LAYER = {
    "confirmation_mode": "protected_only",
    "max_auto_risk": "high",
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
    confirmation_mode = fields.Selection(
        selection=[
            ("always_confirm", "Always confirm"),
            ("risk_based", "Risk based"),
            ("protected_only", "Protected only"),
        ],
        required=True,
        default="protected_only",
    )
    max_auto_risk = fields.Selection(
        selection=[("low", "Low"), ("moderate", "Moderate"), ("high", "High")],
        required=True,
        default="high",
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
        override = _message_override(message)
        record = self.browse()
        if conversation_id:
            record = self.search(
                [
                    ("user_id", "=", self.env.uid),
                    ("conversation_id", "=", conversation_id),
                ],
                limit=1,
            )
            if override.get("reset"):
                record.unlink()
                record = self.browse()
            elif override:
                values = {
                    key: value
                    for key, value in override.items()
                    if key != "reset"
                }
                if record:
                    record.write(values)
                else:
                    values.update(
                        {"conversation_id": conversation_id, "user_id": self.env.uid}
                    )
                    record = self.create(values)
        conversation = _policy_layer(
            mode=(override.get("confirmation_mode") if not record else record.confirmation_mode)
            or "protected_only",
            risk=(override.get("max_auto_risk") if not record else record.max_auto_risk)
            or "high",
            synthetic=(
                override.get("allow_synthetic_data")
                if not record and "allow_synthetic_data" in override
                else record.allow_synthetic_data
                if record
                else True
            ),
        )
        explicit_synthetic = _explicit_synthetic_request(message)
        persisted_synthetic = bool(record and record.synthetic_data_authorized)
        if override.get("synthetic_data_authorized") is True:
            persisted_synthetic = True
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
        parameters = self.env["ir.config_parameter"]
        mode = (
            parameters._get_param("odoo_ai_assistant.agent_confirmation_mode")
            or "protected_only"
        )
        risk = (
            parameters._get_param("odoo_ai_assistant.agent_max_auto_risk")
            or "high"
        )
        raw_synthetic = (
            parameters._get_param("odoo_ai_assistant.agent_allow_synthetic_data")
            or "True"
        )
        return _policy_layer(
            mode=mode if mode in _MODES else "always_confirm",
            risk=risk if risk in _RISKS else "low",
            synthetic=str(raw_synthetic).strip().lower() in {"1", "true", "yes"},
        )


def _policy_layer(*, mode, risk, synthetic):
    return {
        "confirmation_mode": mode,
        "max_auto_risk": risk,
        "allow_synthetic_data": bool(synthetic),
        "max_tool_calls_per_turn": 32,
        "max_write_steps_per_plan": 12,
        "max_replans": 2,
        "max_consecutive_failures": 3,
    }


def _message_override(message):
    if not isinstance(message, str):
        return {}
    normalized = " ".join(message.casefold().split())
    result = {}
    if re.search(r"\b(restablece|reinicia|borra)\b.{0,40}\bpol[ií]tica\b", normalized):
        return {"reset": True}
    if re.search(r"\bconfirma(?:ci[oó]n)? siempre\b", normalized):
        result["confirmation_mode"] = "always_confirm"
    elif re.search(r"\bsolo confirma\b.{0,40}\bproteg", normalized):
        result["confirmation_mode"] = "protected_only"
    elif re.search(r"\bconfirmaci[oó]n por riesgo\b", normalized):
        result["confirmation_mode"] = "risk_based"
    if re.search(r"\bno (?:uses?|crees?)\b.{0,30}\b(?:datos )?sint[eé]tic", normalized):
        result.update(
            {"allow_synthetic_data": False, "synthetic_data_authorized": False}
        )
    elif re.search(
        r"\b(?:puedes|autoriza\w*)\b.{0,35}\b(?:datos )?sint[eé]tic",
        normalized,
    ):
        result.update(
            {"allow_synthetic_data": True, "synthetic_data_authorized": True}
        )
    return result


def _explicit_synthetic_request(message):
    if not isinstance(message, str):
        return False
    normalized = " ".join(message.casefold().split())
    return bool(
        re.search(
            r"\b(prueba|demo|demostraci[oó]n|fictici[oa]s?|sint[eé]tic[oa]s?)\b",
            normalized,
        )
    )
