"""Host-owned P5.7 capabilities for explicit conversation preference changes."""

from __future__ import annotations

import hashlib
import json

from odoo.exceptions import AccessError, ValidationError

from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityRisk,
    CapabilityVerification,
)
from ..decorators import tool

_AUTONOMY_PROFILES = ("inherit", "strict", "balanced", "autonomous", "full_access")
_LANGUAGE_MODES = ("inherit", "automatic", "odoo", "fixed")

_EMPTY_INPUT = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
_PREFERENCES_OUTPUT = {
    "type": "object",
    "properties": {
        "autonomy_profile": {"type": "string"},
        "response_language_mode": {"type": "string"},
        "response_language": {"type": "string"},
    },
    "required": ["autonomy_profile", "response_language_mode", "response_language"],
    "additionalProperties": False,
}
_AUTONOMY_INPUT = {
    "type": "object",
    "properties": {
        "profile": {"type": "string", "enum": list(_AUTONOMY_PROFILES)},
    },
    "required": ["profile"],
    "additionalProperties": False,
}
_AUTONOMY_OUTPUT = {
    "type": "object",
    "properties": {
        "preference": {"type": "string", "enum": ["autonomy"]},
        "profile": {"type": "string", "enum": list(_AUTONOMY_PROFILES)},
    },
    "required": ["preference", "profile"],
    "additionalProperties": False,
}
_LANGUAGE_INPUT = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": list(_LANGUAGE_MODES)},
        "language": {"type": "string", "maxLength": 35},
    },
    "required": ["mode", "language"],
    "additionalProperties": False,
}
_LANGUAGE_OUTPUT = {
    "type": "object",
    "properties": {
        "preference": {"type": "string", "enum": ["response_language"]},
        "mode": {"type": "string", "enum": list(_LANGUAGE_MODES)},
        "language": {"type": "string"},
    },
    "required": ["preference", "mode", "language"],
    "additionalProperties": False,
}


@tool(
    name="assistant.conversation.preferences",
    title="Inspect conversation preferences",
    description=(
        "Read the current Assistant preferences for this conversation: temporary autonomy "
        "override and response-language preference. Use this when the user asks what "
        "conversation-specific settings are active."
    ),
    input_schema=_EMPTY_INPUT,
    output_schema=_PREFERENCES_OUTPUT,
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    max_calls=4,
    tags=("assistant", "conversation", "preferences"),
)
def conversation_preferences(context: CapabilityContext, arguments):
    del arguments
    conversation_id = _conversation_id(context)
    try:
        language = context.env["odoo.ai.conversation"].response_language_preference(
            conversation_id
        )
        autonomy = context.env[
            "odoo.ai.chat.policy"
        ].conversation_autonomy_profile(conversation_id)
    except (AccessError, ValidationError):
        raise CapabilityError("access_denied") from None
    return {
        "autonomy_profile": autonomy or "inherit",
        "response_language_mode": language["mode"],
        "response_language": language["language"],
    }


def _autonomy_preview(context, arguments):
    conversation_id = _conversation_id(context)
    requested = _autonomy(arguments.get("profile"))
    current = _current_autonomy(context, conversation_id)
    return CapabilityPreview(
        summary={
            "preference": "autonomy",
            "current": current,
            "requested": requested,
            "scope": "conversation",
            "applies_to": "future_turns",
            "administrator_ceiling_remains_authoritative": True,
        },
        precondition_fingerprint=_fingerprint(
            {"conversation_id": conversation_id, "autonomy_profile": current}
        ),
    )


def _autonomy_verify(context, arguments):
    conversation_id = _conversation_id(context)
    expected = _autonomy(arguments.get("profile"))
    actual = _current_autonomy(context, conversation_id)
    return CapabilityVerification(
        verified=actual == expected,
        summary={"preference": "autonomy", "profile": actual},
    )


@tool(
    name="assistant.conversation.set_autonomy",
    title="Change conversation autonomy",
    description=(
        "Change the autonomy profile for future turns in this conversation only, or use "
        "inherit to return to the user's default. This is a security-sensitive preference "
        "change: the host always requires explicit human approval, and system/administrator "
        "ceilings still clamp the resulting policy. Never use it unless the user explicitly "
        "asked to change autonomy."
    ),
    input_schema=_AUTONOMY_INPUT,
    output_schema=_AUTONOMY_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.ALWAYS,
    preview=_autonomy_preview,
    verify=_autonomy_verify,
    max_calls=1,
    tags=("assistant", "conversation", "preferences", "autonomy"),
)
def set_conversation_autonomy(context: CapabilityContext, arguments):
    conversation_id = _conversation_id(context)
    profile = _autonomy(arguments.get("profile"))
    try:
        selected = context.env[
            "odoo.ai.chat.policy"
        ].set_conversation_autonomy_profile(
            conversation_id,
            None if profile == "inherit" else profile,
        )
    except (AccessError, ValidationError):
        raise CapabilityError("preference_rejected") from None
    return {"preference": "autonomy", "profile": selected or "inherit"}


def _language_preview(context, arguments):
    conversation_id = _conversation_id(context)
    requested = _language_arguments(arguments)
    current = _current_language(context, conversation_id)
    return CapabilityPreview(
        summary={
            "preference": "response_language",
            "current": current,
            "requested": requested,
            "scope": "conversation",
            "applies_to": "future_turns",
        },
        precondition_fingerprint=_fingerprint(
            {"conversation_id": conversation_id, "response_language": current}
        ),
    )


def _language_verify(context, arguments):
    conversation_id = _conversation_id(context)
    expected = _language_arguments(arguments)
    actual = _current_language(context, conversation_id)
    return CapabilityVerification(
        verified=actual == expected,
        summary={
            "preference": "response_language",
            "mode": actual["mode"],
            "language": actual["language"],
        },
    )


@tool(
    name="assistant.conversation.set_response_language",
    title="Change conversation response language",
    description=(
        "Set the response-language preference for future turns in this conversation. Modes: "
        "inherit clears the conversation override; automatic follows conversational language; "
        "odoo follows the Odoo user's language; fixed requires a language tag such as es, "
        "en, es_ES or pt-BR. Pass an empty language string unless mode is fixed. Only call "
        "this for an explicit user request to change the conversation language preference."
    ),
    input_schema=_LANGUAGE_INPUT,
    output_schema=_LANGUAGE_OUTPUT,
    risk=CapabilityRisk.WRITE_PREVIEW,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.NONE,
    preview=_language_preview,
    verify=_language_verify,
    max_calls=1,
    tags=("assistant", "conversation", "preferences", "language"),
)
def set_response_language(context: CapabilityContext, arguments):
    conversation_id = _conversation_id(context)
    requested = _language_arguments(arguments)
    try:
        selected = context.env[
            "odoo.ai.conversation"
        ].set_response_language_preference(
            conversation_id,
            mode=requested["mode"],
            language=requested["language"],
        )
    except (AccessError, ValidationError):
        raise CapabilityError("preference_rejected") from None
    return {
        "preference": "response_language",
        "mode": selected["mode"],
        "language": selected["language"],
    }


def _conversation_id(context):
    value = context.conversation_id
    if not isinstance(value, str) or not value:
        raise CapabilityError("conversation_required")
    return value


def _autonomy(value):
    if value not in _AUTONOMY_PROFILES:
        raise CapabilityError("invalid_context")
    return value


def _current_autonomy(context, conversation_id):
    try:
        selected = context.env[
            "odoo.ai.chat.policy"
        ].conversation_autonomy_profile(conversation_id)
    except (AccessError, ValidationError):
        raise CapabilityError("access_denied") from None
    return selected or "inherit"


def _language_arguments(arguments):
    mode = arguments.get("mode")
    language = arguments.get("language")
    if mode not in _LANGUAGE_MODES or not isinstance(language, str):
        raise CapabilityError("invalid_context")
    normalized = language.strip()
    if mode != "fixed" and normalized:
        raise CapabilityError("invalid_context")
    if mode == "fixed" and not normalized:
        raise CapabilityError("invalid_context")
    return {"mode": mode, "language": normalized}


def _current_language(context, conversation_id):
    try:
        return context.env["odoo.ai.conversation"].response_language_preference(
            conversation_id
        )
    except (AccessError, ValidationError):
        raise CapabilityError("access_denied") from None


def _fingerprint(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
