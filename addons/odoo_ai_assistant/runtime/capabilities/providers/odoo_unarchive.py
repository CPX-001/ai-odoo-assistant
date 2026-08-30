"""Typed unarchive action and host-only inverse for safe archive state restoration."""

from __future__ import annotations

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

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
from .odoo_actions import (
    _fingerprint,
    _read_values,
    _record,
    _record_target,
    _result,
    _safe_name,
    _write_descriptions,
)

_RECORD_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_id": {"type": "integer", "minimum": 1},
    },
    "required": ["model", "record_id"],
    "additionalProperties": False,
}
_MUTATION_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "record_id": {"type": "integer"},
        "operation": {"type": "string"},
    },
    "required": ["model", "record_id", "operation"],
    "additionalProperties": False,
}
_COMPENSATION_INPUT = {
    "type": "object",
    "properties": {
        "original_capability": {"type": "string", "minLength": 3, "maxLength": 128},
        "original_version": {"type": "string", "minLength": 1, "maxLength": 16},
        "arguments": {"type": "object"},
        "preview": {"type": "object"},
        "result": {"type": "object"},
        "verification": {"type": "object"},
    },
    "required": [
        "original_capability",
        "original_version",
        "arguments",
        "preview",
        "result",
        "verification",
    ],
    "additionalProperties": False,
}
_COMPENSATION_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "record_id": {"type": "integer"},
        "operation": {"type": "string"},
        "verified": {"type": "boolean"},
    },
    "required": ["model", "record_id", "operation", "verified"],
    "additionalProperties": False,
}


def _preview(context, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="write")
    descriptions = _write_descriptions(context, model, ("active",))
    if descriptions["active"].get("type") != "boolean":
        raise CapabilityError("action_not_supported")
    before = _read_values(record, {"active": True}).get("active") is True
    return CapabilityPreview(
        summary={
            "operation": "unarchive",
            "model": model,
            "record_id": record_id,
            "display_name": _safe_name(record),
            "before_active": before,
            "after_active": True,
        },
        precondition_fingerprint=_fingerprint(
            {"model": model, "record_id": record_id, "active": before}
        ),
    )


def _verify(context, arguments):
    result = _result(context, operation="unarchive")
    record = _record(context, result["model"], result["record_id"], access="read")
    return CapabilityVerification(
        verified=_read_values(record, {"active": True}).get("active") is True,
        summary={"model": result["model"], "record_id": result["record_id"]},
    )


@tool(
    name="odoo.record.unarchive",
    title="Unarchive Odoo record",
    description="Unarchive one eligible Odoo record by setting its writable active field to true.",
    input_schema=_RECORD_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "unarchive"),
    preview=_preview,
    verify=_verify,
    max_calls=2,
)
def unarchive_record(context: CapabilityContext, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="write")
    descriptions = _write_descriptions(context, model, ("active",))
    if descriptions["active"].get("type") != "boolean":
        raise CapabilityError("action_not_supported")
    try:
        record.write({"active": True})
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {"model": model, "record_id": record_id, "operation": "unarchive"}


@tool(
    name="odoo.record.unarchive.revert",
    title="Revert Odoo record unarchive",
    description="Host-only compensation for a previously verified odoo.record.unarchive operation.",
    input_schema=_COMPENSATION_INPUT,
    output_schema=_COMPENSATION_OUTPUT,
    risk=CapabilityRisk.HOST,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.HOST,
    approval=CapabilityApproval.NONE,
    tags=("odoo", "host", "compensation"),
    max_calls=12,
    max_input_bytes=64 * 1024,
)
def revert_unarchive_record(context: CapabilityContext, arguments):
    if arguments.get("original_capability") != "odoo.record.unarchive":
        raise CapabilityError("capability_compensation_binding_mismatch")
    original = arguments.get("arguments")
    preview = arguments.get("preview")
    result = arguments.get("result")
    verification = arguments.get("verification")
    if not all(isinstance(item, dict) for item in (original, preview, result, verification)):
        raise CapabilityError("capability_compensation_binding_mismatch")
    model = original.get("model")
    record_id = original.get("record_id")
    before_active = preview.get("before_active")
    if (
        not isinstance(model, str)
        or type(record_id) is not int
        or record_id <= 0
        or type(before_active) is not bool
        or preview.get("model") != model
        or preview.get("record_id") != record_id
        or preview.get("operation") != "unarchive"
        or preview.get("after_active") is not True
        or result.get("model") != model
        or result.get("record_id") != record_id
        or result.get("operation") != "unarchive"
    ):
        raise CapabilityError("capability_compensation_binding_mismatch")
    descriptions = _write_descriptions(context, model, ("active",))
    if descriptions["active"].get("type") != "boolean":
        raise CapabilityError("capability_compensation_unavailable")
    record = _record(context, model, record_id, access="write")
    if _read_values(record, {"active": True}).get("active") is not True:
        raise CapabilityError("capability_compensation_precondition_changed")
    try:
        record.write({"active": before_active})
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("capability_compensation_rejected") from None
    if _read_values(record, {"active": before_active}).get("active") is not before_active:
        raise CapabilityError("capability_compensation_verification_failed")
    return {
        "model": model,
        "record_id": record_id,
        "operation": "unarchive_revert",
        "verified": True,
    }
