"""Odoo-owned per-turn policy layers for agent autonomy."""

from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_MODES = {"always_confirm", "risk_based", "protected_only"}
_RISKS = {"low", "moderate", "high", "protected"}
_MODE_RANK = {"always_confirm": 0, "risk_based": 1, "protected_only": 2}
_RISK_RANK = {"low": 0, "moderate": 1, "high": 2, "protected": 3}
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


def resolve_capability_policy(snapshot):
    """Resolve the stored chat-policy snapshot into one capability-policy input.

    The policy layers remain the source of user/admin/conversation configuration. The
    capability framework consumes only this normalized result and therefore does not
    duplicate layer precedence or autonomy-profile rules.
    """

    if not isinstance(snapshot, dict) or set(snapshot) != {
        "layers",
        "synthetic_data_authorized",
    }:
        raise ValidationError("Invalid Assistant policy snapshot")
    layers = snapshot.get("layers")
    if not isinstance(layers, dict) or set(layers) != {
        "system_ceiling",
        "administrator",
        "user",
        "conversation",
    }:
        raise ValidationError("Invalid Assistant policy layers")

    normalized = [_validated_layer(layers[name]) for name in (
        "system_ceiling",
        "administrator",
        "user",
        "conversation",
    )]
    mode = min(
        (layer["confirmation_mode"] for layer in normalized),
        key=_MODE_RANK.__getitem__,
    )
    risk = min(
        (layer["max_auto_risk"] for layer in normalized),
        key=_RISK_RANK.__getitem__,
    )
    return {
        "confirmation_mode": mode,
        "max_auto_risk": risk,
        "allow_synthetic_data": all(
            layer["allow_synthetic_data"] for layer in normalized
        ),
        "synthetic_data_authorized": bool(snapshot["synthetic_data_authorized"]),
        "max_tool_calls_per_turn": min(
            layer["max_tool_calls_per_turn"] for layer in normalized
        ),
        "max_write_steps_per_plan": min(
            layer["max_write_steps_per_plan"] for layer in normalized
        ),
        "max_replans": min(layer["max_replans"] for layer in normalized),
        "max_consecutive_failures": min(
            layer["max_consecutive_failures"] for layer in normalized
        ),
    }


def _validated_layer(value):
    if not isinstance(value, dict):
        raise ValidationError("Invalid Assistant policy layer")
    required = {
        "confirmation_mode",
        "max_auto_risk",
        "allow_synthetic_data",
        "max_tool_calls_per_turn",
        "max_write_steps_per_plan",
        "max_replans",
        "max_consecutive_failures",
    }
    if set(value) != required:
        raise ValidationError("Invalid Assistant policy layer")
    if value["confirmation_mode"] not in _MODES or value["max_auto_risk"] not in _RISKS:
        raise ValidationError("Invalid Assistant policy layer")
    if type(value["allow_synthetic_data"]) is not bool:
        raise ValidationError("Invalid Assistant policy layer")
    limits = {
        "max_tool_calls_per_turn": (1, 32),
        "max_write_steps_per_plan": (0, 12),
        "max_replans": (0, 2),
        "max_consecutive_failures": (1, 3),
    }
    for key, (minimum, maximum) in limits.items():
        if type(value[key]) is not int or not minimum <= value[key] <= maximum:
            raise ValidationError("Invalid Assistant policy layer")
    return dict(value)


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
