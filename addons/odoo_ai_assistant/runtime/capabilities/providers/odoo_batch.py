"""Bounded multi-record Odoo mutations for the embedded capability runtime."""

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
    _has_access,
    _model_name,
    _model_set,
    _read_values,
    _record,
    _safe_name,
    _validate_values,
    _values,
    _verification_values,
    _write_descriptions,
)

_MAX_BATCH_ROWS = 50
_MAX_BATCH_INPUT_BYTES = 128 * 1024
_MAX_BATCH_OUTPUT_BYTES = 192 * 1024

_BATCH_CREATE_INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["create"]},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "rows": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_BATCH_ROWS,
            "items": {"type": "object"},
        },
    },
    "required": ["operation", "model", "rows"],
    "additionalProperties": False,
}
_BATCH_PATCH_INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["patch"]},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_BATCH_ROWS,
            "items": {"type": "integer", "minimum": 1},
        },
        "values": {"type": "object"},
    },
    "required": ["operation", "model", "record_ids", "values"],
    "additionalProperties": False,
}
_BATCH_DELETE_INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["delete"]},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_BATCH_ROWS,
            "items": {"type": "integer", "minimum": 1},
        },
    },
    "required": ["operation", "model", "record_ids"],
    "additionalProperties": False,
}
_BATCH_OUTPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "model": {"type": "string"},
        "record_ids": {
            "type": "array",
            "maxItems": _MAX_BATCH_ROWS,
            "items": {"type": "integer"},
        },
        "count": {"type": "integer"},
    },
    "required": ["operation", "model", "record_ids", "count"],
    "additionalProperties": False,
}


def _batch_preview(context: CapabilityContext, arguments):
    operation = arguments.get("operation")
    model = _model_name(arguments.get("model"))
    if operation == "create":
        rows = _create_rows(context, model, arguments)
        return CapabilityPreview(
            summary={"operation": operation, "model": model, "rows": rows, "count": len(rows)},
            precondition_fingerprint=_fingerprint(
                {"operation": operation, "model": model, "rows": rows}
            ),
        )
    if operation == "patch":
        record_ids, checked = _patch_input(context, model, arguments)
        records = []
        before = []
        for record_id in record_ids:
            record = _record(context, model, record_id, access="write")
            current = _read_values(record, checked)
            before.append({"record_id": record_id, "values": current})
            records.append(
                {
                    "record_id": record_id,
                    "display_name": _safe_name(record),
                    "changes": [
                        {"field": field, "before": current[field], "after": checked[field]}
                        for field in sorted(checked)
                    ],
                }
            )
        return CapabilityPreview(
            summary={
                "operation": operation,
                "model": model,
                "record_ids": list(record_ids),
                "records": records,
                "count": len(record_ids),
            },
            precondition_fingerprint=_fingerprint(
                {"operation": operation, "model": model, "before": before}
            ),
        )
    if operation == "delete":
        record_ids = _delete_input(model, arguments)
        snapshots = []
        for record_id in record_ids:
            record = _record(context, model, record_id, access="unlink")
            snapshots.append(
                {"record_id": record_id, "display_name": _safe_name(record)}
            )
        return CapabilityPreview(
            summary={
                "operation": operation,
                "model": model,
                "records": snapshots,
                "count": len(record_ids),
            },
            precondition_fingerprint=_fingerprint(
                {"operation": operation, "model": model, "records": snapshots}
            ),
        )
    raise CapabilityError("batch_operation_invalid")


def _batch_verify(context: CapabilityContext, arguments):
    result = _batch_result(context)
    operation = result["operation"]
    model = result["model"]
    record_ids = result["record_ids"]
    if operation == "create":
        rows = _create_rows(context, model, arguments)
        if len(rows) != len(record_ids):
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
        for record_id, expected in zip(record_ids, rows, strict=True):
            record = _record(context, model, record_id, access="read")
            if _read_values(record, expected) != _verification_values(record, expected):
                return CapabilityVerification(
                    verified=False,
                    summary={"model": model, "record_id": record_id},
                )
    elif operation == "patch":
        requested_ids, expected = _patch_input(context, model, arguments)
        if list(requested_ids) != record_ids:
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
        for record_id in record_ids:
            record = _record(context, model, record_id, access="read")
            if _read_values(record, expected) != _verification_values(record, expected):
                return CapabilityVerification(
                    verified=False,
                    summary={"model": model, "record_id": record_id},
                )
    elif operation == "delete":
        requested_ids = _delete_input(model, arguments)
        if list(requested_ids) != record_ids:
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
        if _model_set(context, model).browse(record_ids).exists():
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
    else:
        raise CapabilityError("capability_verification_invalid")
    return CapabilityVerification(
        verified=True,
        summary={"operation": operation, "model": model, "count": len(record_ids)},
    )


@tool(
    name="odoo.records.batch_create",
    title="Create multiple Odoo records",
    description=(
        "Create 1 to 50 records on one eligible Odoo model in one bounded operation. "
        "Use this instead of repeated single-record creates. The host previews every row, verifies "
        "the created records and can safely compensate the batch while none of those records has "
        "been changed afterwards."
    ),
    input_schema=_BATCH_CREATE_INPUT,
    output_schema=_BATCH_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "batch", "write", "create"),
    preview=_batch_preview,
    verify=_batch_verify,
    max_calls=2,
    max_input_bytes=_MAX_BATCH_INPUT_BYTES,
    max_output_bytes=_MAX_BATCH_OUTPUT_BYTES,
)
def batch_create(context: CapabilityContext, arguments):
    return _execute_batch(context, arguments, expected_operation="create")


@tool(
    name="odoo.records.batch_patch",
    title="Update multiple Odoo records",
    description=(
        "Apply the same validated field update to 1 to 50 selected records on one eligible Odoo "
        "model. The host snapshots the affected fields, verifies the write and can compensate the "
        "batch if those written fields still match the verified result."
    ),
    input_schema=_BATCH_PATCH_INPUT,
    output_schema=_BATCH_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "batch", "write", "patch"),
    preview=_batch_preview,
    verify=_batch_verify,
    max_calls=2,
    max_input_bytes=_MAX_BATCH_INPUT_BYTES,
    max_output_bytes=_MAX_BATCH_OUTPUT_BYTES,
)
def batch_patch(context: CapabilityContext, arguments):
    return _execute_batch(context, arguments, expected_operation="patch")


@tool(
    name="odoo.records.batch_mutate",
    title="Delete multiple Odoo records",
    description=(
        "Permanently delete 1 to 50 eligible Odoo records in one bounded operation. This legacy "
        "capability name is retained for compatibility, but it is now delete-only so reversible "
        "batch creates and updates cannot be misclassified as irreversible."
    ),
    input_schema=_BATCH_DELETE_INPUT,
    output_schema=_BATCH_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.ALWAYS,
    tags=("odoo", "action", "batch", "write", "delete"),
    preview=_batch_preview,
    verify=_batch_verify,
    max_calls=1,
    max_input_bytes=_MAX_BATCH_INPUT_BYTES,
    max_output_bytes=_MAX_BATCH_OUTPUT_BYTES,
)
def batch_mutate(context: CapabilityContext, arguments):
    return _execute_batch(context, arguments, expected_operation="delete")


def _execute_batch(context: CapabilityContext, arguments, *, expected_operation):
    operation = arguments.get("operation")
    if operation != expected_operation:
        raise CapabilityError("batch_operation_invalid")
    model = _model_name(arguments.get("model"))
    if operation == "create":
        rows = _create_rows(context, model, arguments)
        model_set = _model_set(context, model)
        try:
            records = model_set.create(rows)
        except (AccessError, MissingError, ValidationError, UserError):
            raise CapabilityError("action_rejected") from None
        record_ids = records.ids
    elif operation == "patch":
        record_ids, checked = _patch_input(context, model, arguments)
        for record_id in record_ids:
            _record(context, model, record_id, access="write")
        try:
            _model_set(context, model).browse(list(record_ids)).write(checked)
        except (AccessError, MissingError, ValidationError, UserError):
            raise CapabilityError("action_rejected") from None
        record_ids = list(record_ids)
    elif operation == "delete":
        record_ids = _delete_input(model, arguments)
        for record_id in record_ids:
            _record(context, model, record_id, access="unlink")
        try:
            _model_set(context, model).browse(list(record_ids)).unlink()
        except (AccessError, MissingError, ValidationError, UserError):
            raise CapabilityError("action_rejected") from None
        record_ids = list(record_ids)
    else:
        raise CapabilityError("batch_operation_invalid")
    if not 1 <= len(record_ids) <= _MAX_BATCH_ROWS:
        raise CapabilityError("capability_output_invalid")
    return {
        "operation": operation,
        "model": model,
        "record_ids": list(record_ids),
        "count": len(record_ids),
    }


def _create_rows(context, model, arguments):
    if set(arguments) != {"operation", "model", "rows"}:
        raise CapabilityError("batch_input_invalid")
    raw_rows = arguments.get("rows")
    if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= _MAX_BATCH_ROWS:
        raise CapabilityError("batch_rows_invalid")
    rows = [_values(row) for row in raw_rows]
    fields = tuple(sorted({field for row in rows for field in row}))
    descriptions = _write_descriptions(context, model, fields)
    model_set = _model_set(context, model)
    if not _has_access(model_set, "create"):
        raise CapabilityError("access_denied")
    return [
        _validate_values(
            context,
            {field: descriptions[field] for field in row},
            row,
        )
        for row in rows
    ]


def _patch_input(context, model, arguments):
    if set(arguments) != {"operation", "model", "record_ids", "values"}:
        raise CapabilityError("batch_input_invalid")
    record_ids = _record_ids(arguments.get("record_ids"))
    values = _values(arguments.get("values"))
    descriptions = _write_descriptions(context, model, tuple(values))
    return record_ids, _validate_values(context, descriptions, values)


def _delete_input(model, arguments):
    del model
    if set(arguments) != {"operation", "model", "record_ids"}:
        raise CapabilityError("batch_input_invalid")
    return _record_ids(arguments.get("record_ids"))


def _record_ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_BATCH_ROWS:
        raise CapabilityError("batch_rows_invalid")
    if any(type(record_id) is not int or record_id <= 0 for record_id in value):
        raise CapabilityError("batch_record_invalid")
    if len(value) != len(set(value)):
        raise CapabilityError("batch_record_duplicate")
    return tuple(value)


def _batch_result(context):
    raw = context.metadata.get("capability_result")
    if not isinstance(raw, dict) or set(raw) != {"operation", "model", "record_ids", "count"}:
        raise CapabilityError("capability_verification_invalid")
    operation = raw.get("operation")
    model = raw.get("model")
    record_ids = raw.get("record_ids")
    count = raw.get("count")
    if operation not in {"create", "patch", "delete"}:
        raise CapabilityError("capability_verification_invalid")
    if not isinstance(model, str) or not isinstance(record_ids, list):
        raise CapabilityError("capability_verification_invalid")
    if type(count) is not int or count != len(record_ids):
        raise CapabilityError("capability_verification_invalid")
    if not 1 <= count <= _MAX_BATCH_ROWS:
        raise CapabilityError("capability_verification_invalid")
    if any(type(record_id) is not int or record_id <= 0 for record_id in record_ids):
        raise CapabilityError("capability_verification_invalid")
    return raw
