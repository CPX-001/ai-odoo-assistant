"""Immutable execution-settings snapshot for persisted Assistant turns."""

from __future__ import annotations

import re
from copy import deepcopy

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..runtime.agent.planning import (
    PlanningStrategyError,
    parse_planning_strategy,
    resolve_planning_strategy,
)
from .chat_policy import resolve_capability_policy

_SETTINGS_FORMAT_VERSION = 3
_REASONING_SETTINGS_FORMAT_VERSION = 2
_LEGACY_SETTINGS_FORMAT_VERSION = 1
_BOUND_SETTINGS_FIELDS = frozenset(
    {"reasoning_model", "reasoning_effort", "policy_payload", "execution_settings_payload"}
)
_AUTONOMY_PROFILES = frozenset({"strict", "balanced", "autonomous", "full_access"})
_EFFORT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_PLANNING_MODES = frozenset({"adaptive", "deliberate", "auto"})


class AssistantTurnSettingsSnapshot(models.Model):
    _inherit = "odoo.ai.turn"

    execution_settings_payload = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """Capture user selectors once while keeping live ACL/capability checks dynamic."""

        prepared = []
        for incoming in vals_list:
            values = dict(incoming)
            # Callers cannot provide a parallel snapshot authority. A normal queued turn already
            # carries host-resolved policy/model/screen/message inputs, so derive the rest here.
            values.pop("execution_settings_payload", None)
            policy = values.get("policy_payload")
            if isinstance(policy, dict) and policy:
                if "reasoning_effort" not in values:
                    effort = _reasoning_effort_for_user(self.env, values.get("user_id"))
                    values["reasoning_effort"] = effort or False
                planning_mode = _planning_mode_for_user(self.env, values.get("user_id"))
                values["execution_settings_payload"] = _build_settings_snapshot(
                    reasoning_model=values.get("reasoning_model"),
                    reasoning_effort=values.get("reasoning_effort"),
                    policy=policy,
                    planning_mode=planning_mode,
                    message=values.get("input_message") or "",
                    screen=values.get("screen_payload") or {},
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
        """Return the validated versioned snapshot for runtime/diagnostics/tests."""

        self.ensure_one()
        snapshot = self.execution_settings_payload
        if not snapshot:
            return None
        validated = _validate_settings_snapshot(snapshot)
        if validated["reasoning_model"] != (self.reasoning_model or None):
            raise ValidationError("Assistant turn settings snapshot does not match model")
        if validated["format_version"] >= _REASONING_SETTINGS_FORMAT_VERSION and validated[
            "reasoning_effort"
        ] != (self.reasoning_effort or None):
            raise ValidationError("Assistant turn settings snapshot does not match reasoning effort")
        if validated["policy"] != (self.policy_payload or {}):
            raise ValidationError("Assistant turn settings snapshot does not match policy")
        return validated


def _build_settings_snapshot(
    *,
    reasoning_model,
    reasoning_effort,
    policy,
    planning_mode="adaptive",
    message="",
    screen=None,
):
    # Reuse existing validators; planning affects orchestration only and never policy/ACL authority.
    resolve_capability_policy(policy)
    effort = reasoning_effort or None
    if effort is not None and (
        not isinstance(effort, str) or _EFFORT_PATTERN.fullmatch(effort) is None
    ):
        raise ValidationError("Invalid Assistant turn reasoning effort")
    try:
        strategy = resolve_planning_strategy(
            planning_mode,
            message=message if isinstance(message, str) else "",
            screen=screen if isinstance(screen, dict) else {},
        )
    except PlanningStrategyError as error:
        raise ValidationError("Invalid Assistant planning strategy") from error
    return {
        "format_version": _SETTINGS_FORMAT_VERSION,
        "reasoning_model": reasoning_model or None,
        "reasoning_effort": effort,
        "autonomy_profile": _autonomy_profile_from_policy(policy),
        "planning_mode": strategy.requested_mode,
        "planning_strategy": strategy.payload(),
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
    reasoning_keys = legacy_keys | {"reasoning_effort"}
    current_keys = reasoning_keys | {"planning_mode", "planning_strategy"}
    if version == _LEGACY_SETTINGS_FORMAT_VERSION:
        if set(value) != legacy_keys:
            raise ValidationError("Invalid Assistant turn settings snapshot")
    elif version == _REASONING_SETTINGS_FORMAT_VERSION:
        if set(value) != reasoning_keys:
            raise ValidationError("Invalid Assistant turn settings snapshot")
        _validate_reasoning_effort(value.get("reasoning_effort"))
    elif version == _SETTINGS_FORMAT_VERSION:
        if set(value) != current_keys:
            raise ValidationError("Invalid Assistant turn settings snapshot")
        _validate_reasoning_effort(value.get("reasoning_effort"))
        planning_mode = value.get("planning_mode")
        if planning_mode not in _PLANNING_MODES:
            raise ValidationError("Invalid Assistant turn planning mode")
        try:
            strategy = parse_planning_strategy(value.get("planning_strategy"))
        except PlanningStrategyError as error:
            raise ValidationError("Invalid Assistant turn planning strategy") from error
        if strategy.requested_mode != planning_mode:
            raise ValidationError("Assistant turn planning strategy does not match mode")
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


def _validate_reasoning_effort(effort):
    if effort is not None and (
        not isinstance(effort, str) or _EFFORT_PATTERN.fullmatch(effort) is None
    ):
        raise ValidationError("Invalid Assistant turn reasoning effort")


def _reasoning_effort_for_user(env, user_id):
    if type(user_id) is not int or user_id <= 0:
        return None
    user = env["res.users"].browse(user_id).exists()
    if not user:
        return None
    preference = env["odoo.ai.user.preference"].with_user(user)
    return preference.current_reasoning_effort()


def _planning_mode_for_user(env, user_id):
    if type(user_id) is not int or user_id <= 0:
        return "adaptive"
    user = env["res.users"].browse(user_id).exists()
    if not user:
        return "adaptive"
    preference = env["odoo.ai.user.preference"].with_user(user)
    getter = getattr(preference, "current_planning_mode", None)
    if not callable(getter):
        return "adaptive"
    mode = getter()
    return mode if mode in _PLANNING_MODES else "adaptive"


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
