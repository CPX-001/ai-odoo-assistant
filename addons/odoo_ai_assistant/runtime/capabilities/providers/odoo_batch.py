"""Bounded multi-record Odoo mutations for the embedded capability runtime."""

from __future__ import annotations

from odoo.exceptions import (
    AccessError,
    MissingError,
    RedirectWarning,
    UserError,
    ValidationError,
)

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
from .odoo_bulk import (
    _BULK_DELETE_RECORD_IDS_SCHEMA,
    _BULK_DELETE_RETAINED_GROUPS_SCHEMA,
    _bulk_delete_preview,
    _protected_delete_records,
    _validated_delete_outcomes,
    bulk_delete,
)

_MAX_BATCH_ROWS = 50
_MAX_BATCH_CALLS_PER_PLAN = 5
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
_BATCH_DELETE_OUTPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["delete"]},
        "model": {"type": "string"},
        "record_ids": {
            "type": "array",
            "maxItems": _MAX_BATCH_ROWS,
            "items": {"type": "integer", "minimum": 1},
        },
        "outcome": {"type": "string", "enum": ["completed", "partial", "blocked"]},
        "count": {"type": "integer", "minimum": 0, "maximum": _MAX_BATCH_ROWS},
        "requested_count": {"type": "integer", "minimum": 1, "maximum": _MAX_BATCH_ROWS},
        "excluded_count": {"type": "integer", "minimum": 0, "maximum": _MAX_BATCH_ROWS},
        "failed_count": {"type": "integer", "minimum": 0, "maximum": _MAX_BATCH_ROWS},
        "failed_record_ids": _BULK_DELETE_RECORD_IDS_SCHEMA,
        "excluded_record_ids": _BULK_DELETE_RECORD_IDS_SCHEMA,
        "retained_groups": _BULK_DELETE_RETAINED_GROUPS_SCHEMA,
        "omitted_retained_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": _MAX_BATCH_ROWS,
        },
        "selection_fingerprint": {"type": "string", "minLength": 71, "maxLength": 71},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": [
        "operation",
        "model",
        "record_ids",
        "outcome",
        "count",
        "requested_count",
        "excluded_count",
        "failed_count",
        "failed_record_ids",
        "excluded_record_ids",
        "retained_groups",
        "omitted_retained_count",
        "selection_fingerprint",
        "content_trust",
    ],
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
        _delete_input(model, arguments)
        return _bulk_delete_preview(context, arguments)
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
        remaining = _model_set(context, model).browse(list(requested_ids)).exists()
        protected = _protected_delete_records(context, model, remaining)
        protected_ids = {item["record"].id for item in protected}
        applied_ids, failed_ids, excluded_ids = _validated_delete_outcomes(
            result,
            model=model,
            record_ids=requested_ids,
            excluded_ids=protected_ids,
        )
        expected_applied = [
            record_id for record_id in requested_ids if record_id in applied_ids
        ]
        if expected_applied != record_ids:
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
        if set(remaining.ids) != failed_ids | excluded_ids:
            return CapabilityVerification(verified=False, summary={"count": len(record_ids)})
    else:
        raise CapabilityError("capability_verification_invalid")
    summary = {"operation": operation, "model": model, "count": len(record_ids)}
    if operation == "delete":
        summary.update(
            {
                "outcome": result["outcome"],
                "requested_count": result["requested_count"],
                "failed_count": result["failed_count"],
                "excluded_count": result["excluded_count"],
            }
        )
    return CapabilityVerification(verified=True, summary=summary)


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
    max_calls=_MAX_BATCH_CALLS_PER_PLAN,
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
    max_calls=_MAX_BATCH_CALLS_PER_PLAN,
    max_input_bytes=_MAX_BATCH_INPUT_BYTES,
    max_output_bytes=_MAX_BATCH_OUTPUT_BYTES,
)
def batch_patch(context: CapabilityContext, arguments):
    return _execute_batch(context, arguments, expected_operation="patch")


@tool(
    name="odoo.records.batch_mutate",
    title="Delete multiple Odoo records",
    description=(
        "Permanently delete 1 to 50 eligible Odoo records with verified continue-on-error "
        "semantics. This legacy capability name is retained for compatibility, but it is now "
        "delete-only so reversible batch creates and updates cannot be misclassified as "
        "irreversible."
    ),
    version="3",
    input_schema=_BATCH_DELETE_INPUT,
    output_schema=_BATCH_DELETE_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.ALWAYS,
    tags=("odoo", "action", "batch", "write", "delete"),
    preview=_batch_preview,
    verify=_batch_verify,
    max_calls=_MAX_BATCH_CALLS_PER_PLAN,
    max_input_bytes=_MAX_BATCH_INPUT_BYTES,
    max_output_bytes=_MAX_BATCH_OUTPUT_BYTES,
    developer_metadata={
        "approval_refinement": "record_id_subset",
        "partial_failure_semantics": "continue_on_error",
    },
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
        except (AccessError, MissingError, RedirectWarning, ValidationError, UserError):
            raise CapabilityError(
                "action_rejected",
                details={"model": model, "operation": "create"},
            ) from None
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
        requested_ids = _delete_input(model, arguments)
        result = bulk_delete(context, arguments)
        retained_ids = set(result["failed_record_ids"]) | set(result["excluded_record_ids"])
        record_ids = [
            record_id for record_id in requested_ids if record_id not in retained_ids
        ]
        if result.get("count") != len(record_ids):
            raise CapabilityError("capability_output_invalid")
        return {**result, "record_ids": record_ids}
    else:
        raise CapabilityError("batch_operation_invalid")
    if not 0 <= len(record_ids) <= _MAX_BATCH_ROWS or (
        operation != "delete" and not record_ids
    ):
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
    if not isinstance(raw, dict):
        raise CapabilityError("capability_verification_invalid")
    operation = raw.get("operation")
    expected_keys = {"operation", "model", "record_ids", "count"}
    if operation == "delete":
        expected_keys.update(
            {
                "outcome",
                "requested_count",
                "excluded_count",
                "failed_count",
                "failed_record_ids",
                "excluded_record_ids",
                "retained_groups",
                "omitted_retained_count",
                "selection_fingerprint",
                "content_trust",
            }
        )
    if set(raw) != expected_keys:
        raise CapabilityError("capability_verification_invalid")
    model = raw.get("model")
    record_ids = raw.get("record_ids")
    count = raw.get("count")
    if operation not in {"create", "patch", "delete"}:
        raise CapabilityError("capability_verification_invalid")
    if not isinstance(model, str) or not isinstance(record_ids, list):
        raise CapabilityError("capability_verification_invalid")
    if type(count) is not int or count != len(record_ids):
        raise CapabilityError("capability_verification_invalid")
    if not (0 if operation == "delete" else 1) <= count <= _MAX_BATCH_ROWS:
        raise CapabilityError("capability_verification_invalid")
    if any(type(record_id) is not int or record_id <= 0 for record_id in record_ids):
        raise CapabilityError("capability_verification_invalid")
    return raw
