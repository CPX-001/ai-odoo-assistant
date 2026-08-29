"""Host-only compensating capabilities for safe built-in Odoo mutations.

These capabilities are never revealed to the model. They consume only the host-persisted original
plan snapshot/result and execute under the current effective user's Environment.
"""

from __future__ import annotations

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityRisk,
)
from ..decorators import tool
from .odoo_actions import (
    _read_values,
    _record,
    _validate_values,
    _write_descriptions,
)

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


def _original(arguments, expected):
    if arguments.get("original_capability") != expected:
        raise CapabilityError("capability_compensation_binding_mismatch")
    original_arguments = arguments.get("arguments")
    preview = arguments.get("preview")
    result = arguments.get("result")
    verification = arguments.get("verification")
    if not all(isinstance(item, dict) for item in (original_arguments, preview, result, verification)):
        raise CapabilityError("capability_compensation_binding_mismatch")
    return original_arguments, preview, result, verification


def _restore_values(descriptions, values):
    """Translate Odoo read-side False nulls back through the write validator safely."""

    normalized = {}
    for field, value in values.items():
        if value is False and descriptions[field].get("type") != "boolean":
            normalized[field] = None
        else:
            normalized[field] = value
    return normalized


@tool(
    name="odoo.record.patch.revert",
    title="Revert Odoo record update",
    description="Host-only compensation for a previously verified odoo.record.patch operation.",
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
def revert_patch_record(context: CapabilityContext, arguments):
    original, preview, result, _verification = _original(arguments, "odoo.record.patch")
    model = original.get("model")
    record_id = original.get("record_id")
    values = original.get("values")
    if (
        not isinstance(model, str)
        or type(record_id) is not int
        or record_id <= 0
        or not isinstance(values, dict)
        or result.get("model") != model
        or result.get("record_id") != record_id
        or result.get("operation") != "patch"
        or preview.get("model") != model
        or preview.get("record_id") != record_id
        or preview.get("operation") != "patch"
    ):
        raise CapabilityError("capability_compensation_binding_mismatch")
    changes = preview.get("changes")
    if not isinstance(changes, list) or len(changes) != len(values):
        raise CapabilityError("capability_compensation_binding_mismatch")
    by_field = {}
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"field", "before", "after"}:
            raise CapabilityError("capability_compensation_binding_mismatch")
        field = change.get("field")
        if not isinstance(field, str) or field in by_field:
            raise CapabilityError("capability_compensation_binding_mismatch")
        by_field[field] = change
    if set(by_field) != set(values):
        raise CapabilityError("capability_compensation_binding_mismatch")

    descriptions = _write_descriptions(context, model, tuple(values))
    expected_after = _validate_values(context, descriptions, values)
    before = {field: by_field[field]["before"] for field in values}
    for field, expected in expected_after.items():
        if by_field[field]["after"] != expected:
            raise CapabilityError("capability_compensation_binding_mismatch")
    restore = _validate_values(context, descriptions, _restore_values(descriptions, before))
    record = _record(context, model, record_id, access="write")
    if _read_values(record, expected_after) != expected_after:
        raise CapabilityError("capability_compensation_precondition_changed")
    try:
        record.write(restore)
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("capability_compensation_rejected") from None
    if _read_values(record, restore) != restore:
        raise CapabilityError("capability_compensation_verification_failed")
    return {
        "model": model,
        "record_id": record_id,
        "operation": "patch_revert",
        "verified": True,
    }


@tool(
    name="odoo.record.archive.revert",
    title="Revert Odoo record archive",
    description="Host-only compensation for a previously verified odoo.record.archive operation.",
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
def revert_archive_record(context: CapabilityContext, arguments):
    original, preview, result, _verification = _original(arguments, "odoo.record.archive")
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
        or preview.get("operation") != "archive"
        or preview.get("after_active") is not False
        or result.get("model") != model
        or result.get("record_id") != record_id
        or result.get("operation") != "archive"
    ):
        raise CapabilityError("capability_compensation_binding_mismatch")
    descriptions = _write_descriptions(context, model, ("active",))
    if descriptions["active"].get("type") != "boolean":
        raise CapabilityError("capability_compensation_unavailable")
    record = _record(context, model, record_id, access="write")
    current = _read_values(record, {"active": False})
    if current.get("active") is not False:
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
        "operation": "archive_revert",
        "verified": True,
    }
