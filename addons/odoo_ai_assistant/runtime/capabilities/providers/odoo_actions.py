"""Typed Odoo mutation capabilities for the embedded plan runtime.

The provider exposes only bounded CRUD/business operations. It never exposes arbitrary ORM
methods, SQL, shell, Python, or sudo. Every handler runs under the effective user Environment.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityResult,
    CapabilityRisk,
    CapabilityVerification,
)
from ..decorators import tool
from ....services.turn_context import (
    TurnContextError,
    agent_model_is_eligible,
    visible_action_preview_fields,
)

_MAX_FIELDS = 16
_MAX_TEXT = 4_000
_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_WRITE_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "integer",
        "many2one",
        "monetary",
        "selection",
        "text",
    }
)

_WRITE_SCHEMA_INPUT = {
    "type": "object",
    "properties": {"model": {"type": "string", "minLength": 1, "maxLength": 128}},
    "required": ["model"],
    "additionalProperties": False,
}
_WRITE_SCHEMA_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "write_access": {"type": "boolean"},
        "create_access": {"type": "boolean"},
        "fields": {
            "type": "array",
            "maxItems": 64,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "type": {"type": "string"},
                    "relation": {"type": "string"},
                    "required": {"type": "boolean"},
                },
                "required": ["name", "label", "type", "relation", "required"],
                "additionalProperties": False,
            },
        },
        "defaults": {"type": "object"},
    },
    "required": ["model", "write_access", "create_access", "fields", "defaults"],
    "additionalProperties": False,
}
_RECORD_VALUES_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_id": {"type": "integer", "minimum": 1},
        "values": {"type": "object"},
    },
    "required": ["model", "record_id", "values"],
    "additionalProperties": False,
}
_CREATE_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "values": {"type": "object"},
    },
    "required": ["model", "values"],
    "additionalProperties": False,
}
_RECORD_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "record_id": {"type": "integer", "minimum": 1},
    },
    "required": ["model", "record_id"],
    "additionalProperties": False,
}
_SALE_CONFIRM_INPUT = {
    "type": "object",
    "properties": {"record_id": {"type": "integer", "minimum": 1}},
    "required": ["record_id"],
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


@tool(
    name="odoo.get_effective_write_schema",
    title="Inspect Odoo write schema",
    description=(
        "Return bounded writable fields and defaults for an eligible Odoo business model "
        "under the effective user's current ACL and field permissions. This does not write."
    ),
    input_schema=_WRITE_SCHEMA_INPUT,
    output_schema=_WRITE_SCHEMA_OUTPUT,
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "action", "schema"),
    max_calls=8,
    max_input_bytes=2 * 1024,
    max_output_bytes=96 * 1024,
)
def get_effective_write_schema(context: CapabilityContext, arguments):
    model = _model_name(arguments.get("model"))
    model_set = _model_set(context, model)
    try:
        allowed = visible_action_preview_fields(context.env, model)
        descriptions = model_set.fields_get(
            allfields=list(allowed),
            attributes=["string", "type", "relation", "required"],
        )
        write_access = _has_access(model_set, "write")
        create_access = _has_access(model_set, "create")
        defaults = model_set.default_get(list(allowed)) if create_access else {}
    except TurnContextError as error:
        raise CapabilityError(error.code) from error
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    fields = []
    for name in allowed:
        description = descriptions.get(name)
        if not isinstance(description, dict) or description.get("type") not in _WRITE_TYPES:
            continue
        fields.append(
            {
                "name": name,
                "label": _label(description.get("string"), name),
                "type": description["type"],
                "relation": (
                    description.get("relation")
                    if isinstance(description.get("relation"), str)
                    else ""
                ),
                "required": description.get("required") is True,
            }
        )
    return {
        "model": model,
        "write_access": write_access,
        "create_access": create_access,
        "fields": fields,
        "defaults": {
            name: _normalize(value)
            for name, value in defaults.items()
            if name in {item["name"] for item in fields}
        },
    }


def _patch_preview(context, arguments):
    model, record_id, values, descriptions, record = _prepare_record_write(context, arguments)
    before = _read_values(record, values)
    checked = _validate_values(context, descriptions, values)
    return CapabilityPreview(
        summary={
            "operation": "patch",
            "model": model,
            "record_id": record_id,
            "display_name": _safe_name(record),
            "changes": [
                {"field": name, "before": before[name], "after": checked[name]}
                for name in sorted(checked)
            ],
        },
        precondition_fingerprint=_fingerprint(
            {"model": model, "record_id": record_id, "before": before}
        ),
    )


def _patch_verify(context, arguments):
    result = _result(context, operation="patch")
    record = _record(context, result["model"], result["record_id"], access="read")
    values = _values(arguments.get("values"))
    descriptions = _write_descriptions(context, result["model"], tuple(values))
    expected = _validate_values(context, descriptions, values)
    actual = _read_values(record, expected)
    return CapabilityVerification(
        verified=actual == expected,
        summary={"model": result["model"], "record_id": result["record_id"]},
    )


@tool(
    name="odoo.record.patch",
    title="Update Odoo record",
    description=(
        "Update up to 16 explicitly writable scalar fields on one eligible Odoo record. "
        "The host previews current values, applies policy/approval, then verifies the write."
    ),
    input_schema=_RECORD_VALUES_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.WRITE,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "write"),
    preview=_patch_preview,
    verify=_patch_verify,
    max_calls=2,
)
def patch_record(context: CapabilityContext, arguments):
    model, record_id, values, descriptions, record = _prepare_record_write(context, arguments)
    checked = _validate_values(context, descriptions, values)
    try:
        record.write(checked)
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {"model": model, "record_id": record_id, "operation": "patch"}


def _create_preview(context, arguments):
    model = _model_name(arguments.get("model"))
    values = _values(arguments.get("values"))
    model_set = _model_set(context, model)
    if not _has_access(model_set, "create"):
        raise CapabilityError("access_denied")
    descriptions = _write_descriptions(context, model, tuple(values))
    checked = _validate_values(context, descriptions, values)
    return CapabilityPreview(
        summary={"operation": "create", "model": model, "values": checked},
        precondition_fingerprint=_fingerprint({"model": model, "values": checked}),
    )


def _create_verify(context, arguments):
    result = _result(context, operation="create")
    record = _record(context, result["model"], result["record_id"], access="read")
    values = _values(arguments.get("values"))
    descriptions = _write_descriptions(context, result["model"], tuple(values))
    expected = _validate_values(context, descriptions, values)
    actual = _read_values(record, expected)
    return CapabilityVerification(
        verified=actual == expected,
        summary={"model": result["model"], "record_id": result["record_id"]},
    )


@tool(
    name="odoo.record.create",
    title="Create Odoo record",
    description=(
        "Create one record on an eligible Odoo business model using up to 16 explicitly "
        "writable scalar fields. Server defaults and ORM rules remain authoritative."
    ),
    input_schema=_CREATE_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.WRITE,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "create"),
    preview=_create_preview,
    verify=_create_verify,
    max_calls=2,
)
def create_record(context: CapabilityContext, arguments):
    model = _model_name(arguments.get("model"))
    values = _values(arguments.get("values"))
    model_set = _model_set(context, model)
    if not _has_access(model_set, "create"):
        raise CapabilityError("access_denied")
    descriptions = _write_descriptions(context, model, tuple(values))
    checked = _validate_values(context, descriptions, values)
    try:
        record = model_set.create(checked)
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {"model": model, "record_id": record.id, "operation": "create"}


def _archive_preview(context, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="write")
    descriptions = _write_descriptions(context, model, ("active",))
    if descriptions["active"].get("type") != "boolean":
        raise CapabilityError("action_not_supported")
    before = bool(record.read(["active"], load=None)[0]["active"])
    return CapabilityPreview(
        summary={
            "operation": "archive",
            "model": model,
            "record_id": record_id,
            "display_name": _safe_name(record),
            "before_active": before,
            "after_active": False,
        },
        precondition_fingerprint=_fingerprint(
            {"model": model, "record_id": record_id, "active": before}
        ),
    )


def _archive_verify(context, arguments):
    result = _result(context, operation="archive")
    record = _record(context, result["model"], result["record_id"], access="read")
    return CapabilityVerification(
        verified=record.read(["active"], load=None)[0]["active"] is False,
        summary={"model": result["model"], "record_id": result["record_id"]},
    )


@tool(
    name="odoo.record.archive",
    title="Archive Odoo record",
    description="Archive one eligible Odoo record by setting its writable active field to false.",
    input_schema=_RECORD_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "archive"),
    preview=_archive_preview,
    verify=_archive_verify,
    max_calls=2,
)
def archive_record(context: CapabilityContext, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="write")
    _write_descriptions(context, model, ("active",))
    try:
        record.write({"active": False})
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {"model": model, "record_id": record_id, "operation": "archive"}


def _delete_preview(context, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="unlink")
    snapshot = {
        "model": model,
        "record_id": record_id,
        "display_name": _safe_name(record),
    }
    return CapabilityPreview(
        summary={"operation": "delete", **snapshot},
        precondition_fingerprint=_fingerprint(snapshot),
    )


def _delete_verify(context, arguments):
    result = _result(context, operation="delete")
    model_set = _model_set(context, result["model"])
    return CapabilityVerification(
        verified=not bool(model_set.browse(result["record_id"]).exists()),
        summary={"model": result["model"], "record_id": result["record_id"]},
    )


@tool(
    name="odoo.record.delete",
    title="Delete Odoo record",
    description=(
        "Permanently delete one eligible Odoo business record. This is irreversible and "
        "always requires explicit human approval before execution."
    ),
    input_schema=_RECORD_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.ALWAYS,
    tags=("odoo", "action", "delete"),
    preview=_delete_preview,
    verify=_delete_verify,
    max_calls=1,
)
def delete_record(context: CapabilityContext, arguments):
    model, record_id = _record_target(arguments)
    record = _record(context, model, record_id, access="unlink")
    try:
        record.unlink()
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {"model": model, "record_id": record_id, "operation": "delete"}


def _confirm_preview(context, arguments):
    record_id = _positive_id(arguments.get("record_id"))
    record = _record(context, "sale.order", record_id, access="write")
    state = record.state
    if state not in {"draft", "sent"}:
        raise CapabilityError("action_precondition_failed")
    snapshot = {
        "model": "sale.order",
        "record_id": record_id,
        "state": state,
        "display_name": _safe_name(record),
    }
    return CapabilityPreview(
        summary={
            "operation": "sale_order_confirm",
            **snapshot,
            "expected_states": ["sale", "done"],
        },
        precondition_fingerprint=_fingerprint(snapshot),
    )


def _confirm_verify(context, arguments):
    result = _result(context, operation="sale_order_confirm")
    record = _record(context, "sale.order", result["record_id"], access="read")
    return CapabilityVerification(
        verified=record.state in {"sale", "done"},
        summary={"model": "sale.order", "record_id": record.id, "state": record.state},
    )


@tool(
    name="odoo.sale_order.confirm",
    title="Confirm sale order",
    description=(
        "Confirm one draft/sent sale order through the explicit Odoo action_confirm business "
        "method. Installed modules may add deliveries, messages or other side effects."
    ),
    input_schema=_SALE_CONFIRM_INPUT,
    output_schema=_MUTATION_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "sale"),
    preview=_confirm_preview,
    verify=_confirm_verify,
    max_calls=1,
)
def confirm_sale_order(context: CapabilityContext, arguments):
    record_id = _positive_id(arguments.get("record_id"))
    record = _record(context, "sale.order", record_id, access="write")
    if record.state not in {"draft", "sent"}:
        raise CapabilityError("action_precondition_failed")
    try:
        record.action_confirm()
    except (AccessError, MissingError, ValidationError, UserError):
        raise CapabilityError("action_rejected") from None
    return {
        "model": "sale.order",
        "record_id": record_id,
        "operation": "sale_order_confirm",
    }


def _prepare_record_write(context, arguments):
    model, record_id = _record_target(arguments)
    values = _values(arguments.get("values"))
    descriptions = _write_descriptions(context, model, tuple(values))
    record = _record(context, model, record_id, access="write")
    return model, record_id, values, descriptions, record


def _write_descriptions(context, model, fields):
    if not 1 <= len(fields) <= _MAX_FIELDS or len(fields) != len(set(fields)):
        raise CapabilityError("action_fields_invalid")
    allowed = set(visible_action_preview_fields(context.env, model))
    if any(field not in allowed for field in fields):
        raise CapabilityError("field_not_writable")
    model_set = _model_set(context, model)
    try:
        descriptions = model_set.fields_get(
            allfields=list(fields),
            attributes=["string", "type", "relation", "required"],
        )
        for field in fields:
            model_set.check_field_access_rights("write", [field])
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    if set(descriptions) != set(fields):
        raise CapabilityError("field_not_writable")
    return descriptions


def _validate_values(context, descriptions, values):
    checked = {}
    for field, value in values.items():
        description = descriptions[field]
        field_type = description.get("type")
        if field_type not in _WRITE_TYPES:
            raise CapabilityError("field_type_not_supported")
        checked[field] = _value(context, description, value)
    return checked


def _value(context, description, value):
    field_type = description["type"]
    if value is None:
        return False
    if field_type == "boolean":
        if type(value) is not bool:
            raise CapabilityError("action_value_invalid")
        return value
    if field_type == "integer":
        if type(value) is not int:
            raise CapabilityError("action_value_invalid")
        return value
    if field_type == "many2one":
        if type(value) is not int or value <= 0:
            raise CapabilityError("action_value_invalid")
        relation = description.get("relation")
        if not isinstance(relation, str) or relation not in context.env:
            raise CapabilityError("action_value_invalid")
        try:
            target = context.env[relation].browse(value).exists()
            target.check_access("read")
        except (AccessError, MissingError, ValidationError):
            raise CapabilityError("access_denied") from None
        if not target:
            raise CapabilityError("action_value_invalid")
        return value
    if field_type in {"float", "monetary"}:
        if type(value) not in {int, float}:
            raise CapabilityError("action_value_invalid")
        return value
    if field_type in {"char", "text", "selection", "date", "datetime"}:
        if not isinstance(value, str) or len(value) > _MAX_TEXT or "\x00" in value:
            raise CapabilityError("action_value_invalid")
        return value
    raise CapabilityError("field_type_not_supported")


def _read_values(record, values):
    fields = tuple(values)
    try:
        rows = record.read(list(fields), load=None)
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    if len(rows) != 1 or rows[0].get("id") != record.id:
        raise CapabilityError("access_denied")
    return {field: _normalize(rows[0].get(field)) for field in fields}


def _record(context, model, record_id, *, access):
    model_set = _model_set(context, model)
    try:
        record = model_set.browse(record_id).exists()
        if not record:
            raise CapabilityError("record_not_found")
        record.check_access(access)
        return record
    except CapabilityError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise CapabilityError("access_denied") from None


def _model_set(context, model):
    if not agent_model_is_eligible(context.env, model):
        raise CapabilityError("action_model_not_allowed")
    try:
        return context.env[model]
    except KeyError:
        raise CapabilityError("action_model_not_allowed") from None


def _has_access(model_set, operation):
    try:
        model_set.browse().check_access(operation)
        return True
    except (AccessError, MissingError, ValidationError):
        return False


def _values(raw):
    if not isinstance(raw, dict) or not 1 <= len(raw) <= _MAX_FIELDS:
        raise CapabilityError("action_values_invalid")
    result = {}
    for field, value in raw.items():
        if not isinstance(field, str) or _FIELD.fullmatch(field) is None:
            raise CapabilityError("action_values_invalid")
        if isinstance(value, (dict, list)):
            raise CapabilityError("action_value_invalid")
        result[field] = value
    return result


def _record_target(arguments):
    return _model_name(arguments.get("model")), _positive_id(arguments.get("record_id"))


def _model_name(value):
    if not isinstance(value, str) or _MODEL.fullmatch(value) is None:
        raise CapabilityError("action_model_not_allowed")
    return value


def _positive_id(value):
    if type(value) is not int or value <= 0:
        raise CapabilityError("action_record_invalid")
    return value


def _result(context, *, operation):
    raw = context.metadata.get("capability_result")
    if not isinstance(raw, dict):
        raise CapabilityError("capability_verification_invalid")
    if raw.get("operation") != operation:
        raise CapabilityError("capability_verification_invalid")
    model = raw.get("model")
    record_id = raw.get("record_id")
    if not isinstance(model, str) or type(record_id) is not int or record_id <= 0:
        raise CapabilityError("capability_verification_invalid")
    return raw


def _fingerprint(value):
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _safe_name(record):
    return " ".join(str(record.display_name or record.id).split())[:240]


def _label(value, fallback):
    if not isinstance(value, str):
        return fallback
    normalized = " ".join(value.split())[:240]
    return normalized or fallback


def _normalize(value):
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_normalize(item) for item in value[:16]]
    if isinstance(value, list):
        return [_normalize(item) for item in value[:32]]
    return str(value)[:2_048]
