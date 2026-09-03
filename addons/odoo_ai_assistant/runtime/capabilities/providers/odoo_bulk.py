"""Bounded high-volume selection and deletion capabilities.

These capabilities remove deterministic paging/chunking work from the model without exposing a
query language or arbitrary ORM method. Schema, ACLs, record rules, preview, approval and
verification remain host-owned.
"""

from __future__ import annotations

from odoo.exceptions import (
    AccessError,
    MissingError,
    RedirectWarning,
    UserError,
    ValidationError,
)
from psycopg2 import IntegrityError, errors

from ....services.turn_context import agent_model_is_eligible
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
from .odoo_actions import _fingerprint, _model_name, _safe_name
from .odoo_actions import _model_set as _action_model_set
from .odoo_query import (
    _FILTER_SCHEMA,
    _bounded_int,
    _domain,
    _effective_schema,
    _order,
    _require_schema_id,
)
from .odoo_query import (
    _model_set as _query_model_set,
)

_MAX_BULK_RECORDS = 500
_MAX_OFFSET = 10_000
_MAX_PREVIEW_RECORDS = 25
_MAX_FAILURE_GROUPS = 10
_MAX_FAILURE_MESSAGE = 160


class _DeleteNotApplied(RuntimeError):
    """Internal marker for an unlink override that returned without deleting."""


_DELETE_REJECTIONS = (
    AccessError,
    MissingError,
    RedirectWarning,
    ValidationError,
    UserError,
    IntegrityError,
    _DeleteNotApplied,
)

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
_BULK_DELETE_RECORD_IDS_SCHEMA = {
    "type": "array",
    "maxItems": _MAX_BULK_RECORDS,
    "items": {"type": "integer", "minimum": 1},
}
_BULK_DELETE_RETAINED_GROUPS_SCHEMA = {
    "type": "array",
    "maxItems": _MAX_FAILURE_GROUPS,
    "items": {
        "type": "object",
        "properties": {
            "state": {"type": "string", "enum": ["failed", "excluded"]},
            "error_code": {"type": "string", "minLength": 1, "maxLength": 64},
            "message": {
                "type": "string",
                "minLength": 1,
                "maxLength": _MAX_FAILURE_MESSAGE,
            },
            "resolution": {"type": "string", "minLength": 1, "maxLength": 64},
            "blocking_model": {"type": "string", "minLength": 1, "maxLength": 128},
            "record_ids": _BULK_DELETE_RECORD_IDS_SCHEMA,
            "count": {"type": "integer", "minimum": 1, "maximum": _MAX_BULK_RECORDS},
        },
        "required": ["state", "error_code", "message", "resolution", "record_ids", "count"],
        "additionalProperties": False,
    },
}
_BULK_DELETE_OUTPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["delete"]},
        "model": {"type": "string"},
        "outcome": {"type": "string", "enum": ["completed", "partial", "blocked"]},
        "count": {"type": "integer", "minimum": 0, "maximum": _MAX_BULK_RECORDS},
        "requested_count": {"type": "integer", "minimum": 1, "maximum": _MAX_BULK_RECORDS},
        "excluded_count": {"type": "integer", "minimum": 0, "maximum": _MAX_BULK_RECORDS},
        "failed_count": {"type": "integer", "minimum": 0, "maximum": _MAX_BULK_RECORDS},
        "failed_record_ids": _BULK_DELETE_RECORD_IDS_SCHEMA,
        "excluded_record_ids": _BULK_DELETE_RECORD_IDS_SCHEMA,
        "retained_groups": _BULK_DELETE_RETAINED_GROUPS_SCHEMA,
        "omitted_retained_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": _MAX_BULK_RECORDS,
        },
        "selection_fingerprint": {"type": "string", "minLength": 71, "maxLength": 71},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": [
        "operation",
        "model",
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
    model, record_ids, records, protected = _bulk_delete_targets(context, arguments)
    sample = [
        {"record_id": record.id, "display_name": _safe_name(record)}
        for record in records[:_MAX_PREVIEW_RECORDS]
    ]
    protected_sample = [
        {
            "record_id": item["record"].id,
            "display_name": _safe_name(item["record"]),
            "reason": item["reason"],
        }
        for item in protected[:_MAX_PREVIEW_RECORDS]
    ]
    fingerprint = _selection_fingerprint(model, record_ids, records.ids)
    return CapabilityPreview(
        summary={
            "operation": "delete",
            "model": model,
            "count": len(records),
            "requested_count": len(record_ids),
            "excluded_count": len(protected),
            "records": sample,
            "protected_records": protected_sample,
            "omitted_count": max(0, len(records) - len(sample)),
        },
        precondition_fingerprint=fingerprint,
    )


def _bulk_delete_verify(context: CapabilityContext, arguments):
    result = context.metadata.get("capability_result")
    model = _model_name(arguments.get("model"))
    record_ids = _record_ids(arguments.get("record_ids"))
    remaining = _action_model_set(context, model).browse(list(record_ids)).exists()
    protected = _protected_delete_records(context, model, remaining)
    protected_ids = {item["record"].id for item in protected}
    applied_ids, failed_ids, excluded_ids = _validated_delete_outcomes(
        result,
        model=model,
        record_ids=record_ids,
        excluded_ids=protected_ids,
    )
    if set(remaining.ids) != failed_ids | excluded_ids:
        raise CapabilityError("capability_verification_invalid")
    return CapabilityVerification(
        verified=True,
        summary={
            "operation": "delete",
            "model": model,
            "outcome": result["outcome"],
            "count": len(applied_ids),
            "requested_count": len(record_ids),
            "failed_count": len(failed_ids),
            "excluded_count": len(excluded_ids),
        },
    )


@tool(
    name="odoo.records.bulk_delete",
    title="Delete many Odoo records",
    description=(
        "Permanently delete 1 to 500 explicit Odoo records with continue-on-error semantics. The "
        "host first uses one efficient recordset operation and, only when Odoo rejects that set, "
        "isolates records with savepoints so unrelated valid deletions continue. The result "
        "reports exact failed/excluded record ids plus bounded grouped reasons, including the "
        "dynamically identified blocking model when it is visible to the effective user."
    ),
    version="3",
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
    max_output_bytes=32 * 1024,
    developer_metadata={
        "approval_refinement": "record_id_subset",
        "partial_failure_semantics": "continue_on_error",
    },
)
def bulk_delete(context: CapabilityContext, arguments):
    model, record_ids, records, protected = _bulk_delete_targets(context, arguments)
    fingerprint = _selection_fingerprint(model, record_ids, records.ids)
    attempted = _delete_with_row_fallback(context, model, tuple(records.ids), records)
    by_id = {item["record_id"]: item for item in attempted}
    for item in protected:
        protected_result = _excluded_delete_result(item)
        by_id[protected_result["record_id"]] = protected_result
    results = [by_id[record_id] for record_id in record_ids]
    failed_count = sum(item["state"] == "failed" for item in results)
    excluded_count = len(protected)
    count = len(results) - failed_count - excluded_count
    compact = _compact_delete_results(results)
    return {
        "operation": "delete",
        "model": model,
        "outcome": _delete_outcome(count, failed_count + excluded_count),
        "count": count,
        "requested_count": len(record_ids),
        "excluded_count": excluded_count,
        "failed_count": failed_count,
        **compact,
        "selection_fingerprint": fingerprint,
        "content_trust": "untrusted",
    }


def _bulk_delete_targets(context, arguments):
    if (
        set(arguments) != {"operation", "model", "record_ids"}
        or arguments.get("operation") != "delete"
    ):
        raise CapabilityError("bulk_delete_input_invalid")
    model = _model_name(arguments.get("model"))
    record_ids = _record_ids(arguments.get("record_ids"))
    model_set = _action_model_set(context, model)
    try:
        records = model_set.browse(list(record_ids)).exists()
        if len(records) != len(record_ids) or set(records.ids) != set(record_ids):
            raise CapabilityError("record_not_found")
        records.check_access("read")
    except CapabilityError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise CapabilityError("access_denied") from None
    protected = _protected_delete_records(context, model, records)
    protected_ids = {item["record"].id for item in protected}
    eligible = records.filtered(lambda record: record.id not in protected_ids)
    try:
        model_set.browse().check_access("unlink")
    except (AccessError, MissingError, ValidationError):
        raise CapabilityError("access_denied") from None
    return model, record_ids, eligible, protected


def _protected_delete_records(context, model, records):
    if model != "res.partner" or not records:
        return []
    record_ids = records.ids
    active_users = context.env["res.users"].search(
        [("active", "=", True), ("partner_id", "in", record_ids)]
    )
    user_partner_ids = set(active_users.mapped("partner_id").ids)
    companies = context.env["res.company"].search([("partner_id", "in", record_ids)])
    company_partner_ids = set(companies.mapped("partner_id").ids)
    protected = []
    for record in records:
        reasons = []
        if record.id in user_partner_ids:
            reasons.append("linked_active_user")
        if record.id in company_partner_ids:
            reasons.append("company_partner")
        if reasons:
            protected.append({"record": record, "reason": "+".join(reasons)})
    return protected


def _delete_with_row_fallback(context, model, record_ids, records):
    """Delete efficiently, then isolate normal Odoo rejections without aborting the turn."""

    if not records:
        return []
    try:
        with context.env.cr.savepoint():
            records.unlink()
    except _DELETE_REJECTIONS:
        pass
    else:
        remaining_ids = set(_action_model_set(context, model).browse(list(record_ids)).exists().ids)
        if not remaining_ids:
            return [_applied_delete_result(record_id) for record_id in record_ids]

    results = []
    model_set = _action_model_set(context, model)
    blocking_model_cache = {}
    for record_id in record_ids:
        try:
            with context.env.cr.savepoint():
                record = model_set.browse(record_id).exists()
                if not record:
                    results.append(_applied_delete_result(record_id))
                    continue
                record.unlink()
                if model_set.browse(record_id).exists():
                    raise _DeleteNotApplied()
        except _DELETE_REJECTIONS as error:
            results.append(
                _failed_delete_result(
                    context,
                    record_id=record_id,
                    error=error,
                    blocking_model_cache=blocking_model_cache,
                )
            )
        else:
            results.append(_applied_delete_result(record_id))

    remaining_ids = set(model_set.browse(list(record_ids)).exists().ids)
    normalized = []
    for item in results:
        if item["record_id"] not in remaining_ids:
            normalized.append(_applied_delete_result(item["record_id"]))
        elif item["state"] == "failed":
            normalized.append(item)
        else:
            normalized.append(
                _failed_delete_result(
                    context,
                    record_id=item["record_id"],
                    error=_DeleteNotApplied(),
                )
            )
    return normalized


def _applied_delete_result(record_id):
    return {"record_id": record_id, "state": "applied"}


def _excluded_delete_result(item):
    return {
        "record_id": item["record"].id,
        "state": "excluded",
        "error_code": f"protected_{item['reason']}",
        "message": "The host excluded this operationally protected Odoo record.",
        "resolution": "keep_protected_record",
    }


def _failed_delete_result(
    context,
    *,
    record_id,
    error,
    blocking_model_cache=None,
):
    code, message, resolution = _delete_failure(error)
    result = {
        "record_id": record_id,
        "state": "failed",
        "error_code": code,
        "message": message,
        "resolution": resolution,
    }
    if isinstance(error, IntegrityError):
        blocking_model = _blocking_model(context, error, blocking_model_cache)
        if blocking_model:
            result["blocking_model"] = blocking_model
    return result


def _compact_delete_results(results):
    failed_record_ids = [
        item["record_id"] for item in results if item["state"] == "failed"
    ]
    excluded_record_ids = [
        item["record_id"] for item in results if item["state"] == "excluded"
    ]
    grouped = {}
    for item in results:
        if item["state"] == "applied":
            continue
        key = (
            item["state"],
            item["error_code"],
            item["message"],
            item["resolution"],
            item.get("blocking_model", ""),
        )
        group = grouped.setdefault(
            key,
            {
                "state": item["state"],
                "error_code": item["error_code"],
                "message": item["message"],
                "resolution": item["resolution"],
                "record_ids": [],
                "count": 0,
            },
        )
        if item.get("blocking_model"):
            group["blocking_model"] = item["blocking_model"]
        group["record_ids"].append(item["record_id"])
        group["count"] += 1
    retained_groups = list(grouped.values())[:_MAX_FAILURE_GROUPS]
    detailed_count = sum(item["count"] for item in retained_groups)
    return {
        "failed_record_ids": failed_record_ids,
        "excluded_record_ids": excluded_record_ids,
        "retained_groups": retained_groups,
        "omitted_retained_count": (
            len(failed_record_ids) + len(excluded_record_ids) - detailed_count
        ),
    }


def _delete_failure(error):
    if isinstance(error, AccessError):
        return (
            "access_denied",
            "The effective Odoo user is not allowed to delete this record.",
            "request_access_or_keep",
        )
    if isinstance(error, MissingError):
        return (
            "record_not_found",
            "The record changed or disappeared while Odoo was processing the deletion.",
            "refresh_selection",
        )
    if isinstance(error, errors.ForeignKeyViolation):
        return (
            "record_is_referenced",
            "Another Odoo record requires this record.",
            "archive_or_remove_dependencies",
        )
    if isinstance(error, IntegrityError):
        return (
            "integrity_constraint",
            "Deleting this record would violate an Odoo data constraint.",
            "review_dependencies",
        )
    if isinstance(error, RedirectWarning):
        return (
            "business_rule_rejected",
            _sanitized_user_message(error),
            "follow_odoo_resolution",
        )
    if isinstance(error, (ValidationError, UserError)):
        return (
            "business_rule_rejected",
            _sanitized_user_message(error),
            "review_business_rule",
        )
    if isinstance(error, _DeleteNotApplied):
        return (
            "operation_not_applied",
            "Odoo completed the call without deleting this record.",
            "review_business_rule",
        )
    return (
        "operation_failed",
        "Odoo could not complete the delete operation for this record.",
        "retry_or_review_logs",
    )


def _sanitized_user_message(error):
    message = error.args[0] if error.args and isinstance(error.args[0], str) else ""
    normalized = " ".join(message.split())[:_MAX_FAILURE_MESSAGE]
    return normalized or "Odoo rejected the deletion because of a business rule."


def _blocking_model(context, error, cache=None):
    diag = getattr(error, "diag", None)
    table = getattr(diag, "table_name", None)
    if not isinstance(table, str) or not table:
        return ""
    cache = cache if isinstance(cache, dict) else {}
    if table in cache:
        return cache[table]
    candidates = sorted(
        model_name
        for model_name, model_class in context.env.registry.items()
        if getattr(model_class, "_table", None) == table
        and _blocking_model_is_visible(context, model_name)
    )
    cache[table] = candidates[0] if candidates else ""
    return cache[table]


def _blocking_model_is_visible(context, model):
    try:
        if not context.env[model].browse().has_access("read"):
            return False
    except Exception:  # noqa: BLE001 - optional diagnostic metadata fails closed
        return False
    return agent_model_is_eligible(context.env, model)


def _delete_outcome(applied_count, failed_count):
    if not failed_count:
        return "completed"
    return "partial" if applied_count else "blocked"


def _validated_delete_outcomes(result, *, model, record_ids, excluded_ids=()):
    excluded_ids = set(excluded_ids)
    eligible_ids = [record_id for record_id in record_ids if record_id not in excluded_ids]
    expected_fingerprint = _selection_fingerprint(model, record_ids, eligible_ids)
    if (
        not isinstance(result, dict)
        or result.get("operation") != "delete"
        or result.get("model") != model
        or result.get("requested_count") != len(record_ids)
        or result.get("excluded_count") != len(excluded_ids)
        or result.get("selection_fingerprint") != expected_fingerprint
        or result.get("content_trust") != "untrusted"
    ):
        raise CapabilityError("capability_verification_invalid")
    failed_record_ids = result.get("failed_record_ids")
    excluded_record_ids = result.get("excluded_record_ids")
    if not _valid_result_ids(failed_record_ids) or not _valid_result_ids(excluded_record_ids):
        raise CapabilityError("capability_verification_invalid")
    failed_ids = set(failed_record_ids)
    actual_excluded_ids = set(excluded_record_ids)
    applied_ids = set(record_ids) - failed_ids - actual_excluded_ids
    if (
        applied_ids | failed_ids | actual_excluded_ids != set(record_ids)
        or applied_ids & failed_ids
        or applied_ids & actual_excluded_ids
        or failed_ids & actual_excluded_ids
        or actual_excluded_ids != excluded_ids
    ):
        raise CapabilityError("capability_verification_invalid")
    retained_groups = result.get("retained_groups")
    if not isinstance(retained_groups, list) or len(retained_groups) > _MAX_FAILURE_GROUPS:
        raise CapabilityError("capability_verification_invalid")
    detailed_ids = []
    for group in retained_groups:
        if not isinstance(group, dict) or not _valid_result_ids(group.get("record_ids")):
            raise CapabilityError("capability_verification_invalid")
        group_ids = group["record_ids"]
        expected_state_ids = failed_ids if group.get("state") == "failed" else actual_excluded_ids
        if group.get("count") != len(group_ids) or not set(group_ids) <= expected_state_ids:
            raise CapabilityError("capability_verification_invalid")
        detailed_ids.extend(group_ids)
    if len(detailed_ids) != len(set(detailed_ids)):
        raise CapabilityError("capability_verification_invalid")
    if result.get("omitted_retained_count") != (
        len(failed_ids) + len(actual_excluded_ids) - len(detailed_ids)
    ):
        raise CapabilityError("capability_verification_invalid")
    applied_count = len(applied_ids)
    failed_count = len(failed_ids)
    if (
        result.get("count") != applied_count
        or result.get("failed_count") != failed_count
        or result.get("outcome")
        != _delete_outcome(applied_count, failed_count + len(excluded_ids))
    ):
        raise CapabilityError("capability_verification_invalid")
    return applied_ids, failed_ids, actual_excluded_ids


def _valid_result_ids(value):
    return (
        isinstance(value, list)
        and len(value) <= _MAX_BULK_RECORDS
        and all(type(record_id) is int and record_id > 0 for record_id in value)
        and len(value) == len(set(value))
    )


def _record_ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_BULK_RECORDS:
        raise CapabilityError("bulk_record_ids_invalid")
    if any(type(record_id) is not int or record_id <= 0 for record_id in value):
        raise CapabilityError("bulk_record_ids_invalid")
    if len(value) != len(set(value)):
        raise CapabilityError("bulk_record_ids_duplicate")
    return tuple(value)


def _selection_fingerprint(model, record_ids, eligible_ids):
    return _fingerprint(
        {
            "model": model,
            "record_ids": list(record_ids),
            "eligible_ids": list(eligible_ids),
            "operation": "delete",
        }
    )
