"""P5.3 immutable execution-settings snapshot for persisted Assistant turns."""

from __future__ import annotations

import re
from copy import deepcopy

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .chat_policy import resolve_capability_policy

_SETTINGS_FORMAT_VERSION = 2
_LEGACY_SETTINGS_FORMAT_VERSION = 1
_BOUND_SETTINGS_FIELDS = frozenset(
    {"reasoning_model", "reasoning_effort", "policy_payload", "execution_settings_payload"}
)
_AUTONOMY_PROFILES = frozenset({"strict", "balanced", "autonomous", "full_access"})
_EFFORT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class AssistantTurnSettingsSnapshot(models.Model):
    _inherit = "odoo.ai.turn"

    execution_settings_payload = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """Capture product selectors from the already host-resolved turn inputs.

        The queue resolves model and policy under the originating user before creating
        the turn. Reasoning effort is read from the same user's Odoo-owned preference at
        this creation boundary. P5.3 then binds those values into one versioned snapshot
        without freezing dynamic ACL/record-rule/capability availability checks.
        """

        prepared = []
        for incoming in vals_list:
            values = dict(incoming)
            # Callers cannot provide a parallel snapshot authority. When a normal queued
            # turn carries a resolved policy, the host derives the snapshot itself.
            values.pop("execution_settings_payload", None)
            policy = values.get("policy_payload")
            if isinstance(policy, dict) and policy:
                if "reasoning_effort" not in values:
                    effort = _reasoning_effort_for_user(self.env, values.get("user_id"))
                    values["reasoning_effort"] = effort or False
                values["execution_settings_payload"] = _build_settings_snapshot(
                    reasoning_model=values.get("reasoning_model"),
                    reasoning_effort=values.get("reasoning_effort"),
                    policy=policy,
                )
            prepared.append(values)
        return super().create(prepared)

    def write(self, values):
        """Keep captured execution selectors immutable for the life of the turn."""

        if _BOUND_SETTINGS_FIELDS.intersection(values) and any(
            record.execution_settings_payload for record in self
        ):
            raise ValidationError("Assistant turn execution settings are immutable")
        return super().write(values)

    def execution_settings_snapshot(self):
        """Return the validated versioned snapshot for diagnostics/tests/future consumers."""

        self.ensure_one()
        snapshot = self.execution_settings_payload
        if not snapshot:
            return None
        validated = _validate_settings_snapshot(snapshot)
        if validated["reasoning_model"] != (self.reasoning_model or None):
            raise ValidationError("Assistant turn settings snapshot does not match model")
        if validated["format_version"] >= 2 and validated["reasoning_effort"] != (
            self.reasoning_effort or None
        ):
            raise ValidationError("Assistant turn settings snapshot does not match reasoning effort")
        if validated["policy"] != (self.policy_payload or {}):
            raise ValidationError("Assistant turn settings snapshot does not match policy")
        return validated


def _build_settings_snapshot(*, reasoning_model, reasoning_effort, policy):
    # Reuse the existing policy validator instead of creating a second policy schema.
    resolve_capability_policy(policy)
    effort = reasoning_effort or None
    if effort is not None and (
        not isinstance(effort, str) or _EFFORT_PATTERN.fullmatch(effort) is None
    ):
        raise ValidationError("Invalid Assistant turn reasoning effort")
    return {
        "format_version": _SETTINGS_FORMAT_VERSION,
        "reasoning_model": reasoning_model or None,
        "reasoning_effort": effort,
        "autonomy_profile": _autonomy_profile_from_policy(policy),
        "policy": deepcopy(policy),
    }


def _validate_settings_snapshot(value):
    if not isinstance(value, dict):
        raise ValidationError("Invalid Assistant turn settings snapshot")
    version = value.get("format_version")
    legacy_keys = {
        "format_version",
        "reasoning_model",
        "autonomy_profile",
        "policy",
    }
    current_keys = legacy_keys | {"reasoning_effort"}
    if version == _LEGACY_SETTINGS_FORMAT_VERSION:
        if set(value) != legacy_keys:
            raise ValidationError("Invalid Assistant turn settings snapshot")
    elif version == _SETTINGS_FORMAT_VERSION:
        if set(value) != current_keys:
            raise ValidationError("Invalid Assistant turn settings snapshot")
        effort = value.get("reasoning_effort")
        if effort is not None and (
            not isinstance(effort, str) or _EFFORT_PATTERN.fullmatch(effort) is None
        ):
            raise ValidationError("Invalid Assistant turn reasoning effort")
    else:
        raise ValidationError("Unsupported Assistant turn settings snapshot")

    model = value.get("reasoning_model")
    if model is not None and (not isinstance(model, str) or not 1 <= len(model) <= 128):
        raise ValidationError("Invalid Assistant turn settings model")
    profile = value.get("autonomy_profile")
    if profile not in _AUTONOMY_PROFILES:
        raise ValidationError("Invalid Assistant turn autonomy snapshot")
    policy = value.get("policy")
    resolve_capability_policy(policy)
    if profile != _autonomy_profile_from_policy(policy):
        raise ValidationError("Assistant turn autonomy snapshot does not match policy")
    return deepcopy(value)


def _reasoning_effort_for_user(env, user_id):
    if type(user_id) is not int or user_id <= 0:
        return None
    user = env["res.users"].browse(user_id).exists()
    if not user:
        return None
    preference = env["odoo.ai.user.preference"].with_user(user)
    return preference.current_reasoning_effort()


def _autonomy_profile_from_policy(policy):
    layers = policy.get("layers") if isinstance(policy, dict) else None
    user = layers.get("user") if isinstance(layers, dict) else None
    if not isinstance(user, dict):
        raise ValidationError("Invalid Assistant policy snapshot")
    mode = user.get("confirmation_mode")
    risk = user.get("max_auto_risk")
    if mode == "always_confirm":
        return "strict"
    if mode == "protected_only" and risk == "protected":
        return "full_access"
    if mode == "protected_only":
        return "autonomous"
    return "balanced"
