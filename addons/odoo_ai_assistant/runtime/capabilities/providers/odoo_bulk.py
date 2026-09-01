"""Bounded high-volume selection and deletion capabilities.

These capabilities remove deterministic paging/chunking work from the model without exposing a
query language or arbitrary ORM method. Schema, ACLs, record rules, preview, approval and
verification remain host-owned.
"""

from __future__ import annotations

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from ..contracts import (
    CapabilityActivitySpec,
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
from .odoo_actions import _fingerprint, _model_name, _model_set as _action_model_set, _safe_name
from .odoo_query import (
    _FILTER_SCHEMA,
    _bounded_int,
    _domain,
    _effective_schema,
    _model_set as _query_model_set,
    _order,
    _require_schema_id,
)

_MAX_BULK_RECORDS = 500
_MAX_OFFSET = 10_000
_MAX_PREVIEW_RECORDS = 25

_ID_QUERY_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "schema_id": {"type": "string", "minLength": 71, "maxLength": 71},
        "filter": _FILTER_SCHEMA,
        "order": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "direction": {"type": "string", "enum": ["asc", "desc"]},
                },
                "required": ["field", "direction"],
                "additionalProperties": False,
            },
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_BULK_RECORDS},
        "offset": {"type": "integer", "minimum": 0, "maximum": _MAX_OFFSET},
    },
    "required": ["model", "schema_id"],
    "additionalProperties": False,
}
_ID_QUERY_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "schema_id": {"type": "string"},
        "record_ids": {
            "type": "array",
            "maxItems": _MAX_BULK_RECORDS,
            "items": {"type": "integer", "minimum": 1},
        },
        "returned_count": {"type": "integer"},
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
        "next_offset": {"type": ["integer", "null"]},
        "truncated": {"type": "boolean"},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": [
        "model",
        "schema_id",
        "record_ids",
        "returned_count",
        "limit",
        "offset",
        "next_offset",
        "truncated",
        "content_trust",
    ],
    "additionalProperties": False,
}
_BULK_DELETE_INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["delete"]},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_BULK_RECORDS,
            "items": {"type": "integer", "minimum": 1},
        },
    },
    "required": ["operation", "model", "record_ids"],
    "additionalProperties": False,
}
_BULK_DELETE_OUTPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["delete"]},
        "model": {"type": "string"},
        "count": {"type": "integer", "minimum": 1, "maximum": _MAX_BULK_RECORDS},
        "selection_fingerprint": {"type": "string", "minLength": 71, "maxLength": 71},
    },
    "required": ["operation", "model", "count", "selection_fingerprint"],
    "additionalProperties": False,
}


def _selection_activity(_context, arguments):
    limit = arguments.get("limit")
    return {"limit": limit} if type(limit) is int else {}


@tool(
    name="odoo.query_record_ids",
    title="Select Odoo record identities",
    description=(
        "Select up to 500 Odoo record ids for a schema-validated exact bulk workflow without "
        "reading unnecessary business fields. Use only after the model/filter is grounded; use "
        "odoo.query_records instead when field values are needed for judgment."
    ),
    input_schema=_ID_QUERY_INPUT,
    output_schema=_ID_QUERY_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "bulk", "records"),
    activity=CapabilityActivitySpec(
        operation="odoo.records.select",
        headline_code="activity.query.records",
        projector=_selection_activity,
    ),
    max_calls=8,
    max_input_bytes=16 * 1024,
    max_output_bytes=32 * 1024,
)
def query_record_ids(context: CapabilityContext, arguments):
    schema = _effective_schema(context, arguments.get("model"))
    _require_schema_id(arguments.get("schema_id"), schema["schema_id"])
    metadata = {item["name"]: item for item in schema["fields"]}
    domain = _domain(arguments.get("filter"), metadata)
    order = _order(arguments.get("order"), metadata)
    limit = _bounded_int(arguments.get("limit", _MAX_BULK_RECORDS), 1, _MAX_BULK_RECORDS)
    offset = _bounded_int(arguments.get("offset", 0), 0, _MAX_OFFSET)
    model_set = _query_model_set(context, schema["model"])
    try:
        model_set.browse().check_access("read")
        stable_order = f"{order}, id asc" if order else "id asc"
        records = model_set.search(domain, order=stable_order, limit=limit + 1, offset=offset)
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    except ValueError:
        raise CapabilityError("invalid_query") from None
    truncated = len(records) > limit
    record_ids = records[:limit].ids
    return {
        "model": schema["model"],
        "schema_id": schema["schema_id"],
        "record_ids": record_ids,
        "returned_count": len(record_ids),
        "limit": limit,
        "offset": offset,
        "next_offset": offset + len(record_ids) if truncated else None,
        "truncated": truncated,
        "content_trust": "untrusted",
    }


def _bulk_delete_preview(context: CapabilityContext, arguments):
    model, record_ids, records = _bulk_delete_targets(context, arguments)
    sample = [
        {"record_id": record.id, "display_name": _safe_name(record)}
        for record in records[:_MAX_PREVIEW_RECORDS]
    ]
    fingerprint = _selection_fingerprint(model, record_ids)
    return CapabilityPreview(
        summary={
            "operation": "delete",
            "model": model,
            "count": len(record_ids),
            "records": sample,
            "omitted_count": max(0, len(record_ids) - len(sample)),
        },
        precondition_fingerprint=fingerprint,
    )


def _bulk_delete_verify(context: CapabilityContext, arguments):
    result = context.metadata.get("capability_result")
    model = _model_name(arguments.get("model"))
    record_ids = _record_ids(arguments.get("record_ids"))
    expected_fingerprint = _selection_fingerprint(model, record_ids)
    if (
        not isinstance(result, dict)
        or result.get("operation") != "delete"
        or result.get("model") != model
        or result.get("count") != len(record_ids)
        or result.get("selection_fingerprint") != expected_fingerprint
    ):
        raise CapabilityError("capability_verification_invalid")
    model_set = _action_model_set(context, model)
    remaining = model_set.browse(list(record_ids)).exists()
    return CapabilityVerification(
        verified=not bool(remaining),
        summary={"operation": "delete", "model": model, "count": len(record_ids)},
    )


@tool(
    name="odoo.records.bulk_delete",
    title="Delete many Odoo records",
    description=(
        "Permanently delete 1 to 500 explicit eligible Odoo records in one bounded recordset "
        "operation. The host validates every target, previews a bounded sample, always requires "
        "human approval and verifies that all selected records are absent afterwards."
    ),
    input_schema=_BULK_DELETE_INPUT,
    output_schema=_BULK_DELETE_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.ALWAYS,
    tags=("odoo", "action", "bulk", "write", "delete"),
    preview=_bulk_delete_preview,
    verify=_bulk_delete_verify,
    max_calls=5,
    max_input_bytes=64 * 1024,
    max_output_bytes=16 * 1024,
)
def bulk_delete(context: CapabilityContext, arguments):
    model, record_ids, records = _bulk_delete_targets(context, arguments)
    fingerprint = _selection_fingerprint(model, record_ids)
    try:
        records.unlink()
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {
        "operation": "delete",
        "model": model,
        "count": len(record_ids),
        "selection_fingerprint": fingerprint,
    }


def _bulk_delete_targets(context, arguments):
    if set(arguments) != {"operation", "model", "record_ids"} or arguments.get("operation") != "delete":
        raise CapabilityError("bulk_delete_input_invalid")
    model = _model_name(arguments.get("model"))
    record_ids = _record_ids(arguments.get("record_ids"))
    model_set = _action_model_set(context, model)
    try:
        records = model_set.browse(list(record_ids)).exists()
        if len(records) != len(record_ids) or set(records.ids) != set(record_ids):
            raise CapabilityError("record_not_found")
        records.check_access("unlink")
    except CapabilityError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise CapabilityError("access_denied") from None
    return model, record_ids, records


def _record_ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_BULK_RECORDS:
        raise CapabilityError("bulk_record_ids_invalid")
    if any(type(record_id) is not int or record_id <= 0 for record_id in value):
        raise CapabilityError("bulk_record_ids_invalid")
    if len(value) != len(set(value)):
        raise CapabilityError("bulk_record_ids_duplicate")
    return tuple(value)


def _selection_fingerprint(model, record_ids):
    return _fingerprint({"model": model, "record_ids": list(record_ids), "operation": "delete"})
