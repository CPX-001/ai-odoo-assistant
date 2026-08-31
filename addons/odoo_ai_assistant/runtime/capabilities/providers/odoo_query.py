"""Odoo query capabilities executed directly under the effective Odoo Environment."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime

from odoo.exceptions import AccessError, MissingError, ValidationError

from ....services.turn_context import (
    TurnContextError,
    agent_model_is_eligible,
    search_agent_models,
    visible_query_fields,
)
from ..contracts import (
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityResult,
    CapabilityRisk,
)
from ..decorators import tool

_MAX_FIELDS = 16
_MAX_CONDITIONS = 8
_MAX_SORTS = 3
_MAX_RECORDS = 50
_MAX_GROUP_BY = 2
_MAX_METRICS = 8
_MAX_GROUPS = 50
_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_SCHEMA_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_FILTER_OPERATORS = {
    "boolean": frozenset({"eq", "ne", "in", "not_in"}),
    "char": frozenset({"eq", "ne", "in", "not_in", "contains"}),
    "date": frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}),
    "datetime": frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}),
    "float": frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}),
    "html": frozenset({"eq", "ne", "contains"}),
    "integer": frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}),
    "many2one": frozenset({"eq", "ne", "in", "not_in"}),
    "monetary": frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}),
    "selection": frozenset({"eq", "ne", "in", "not_in"}),
    "text": frozenset({"eq", "ne", "contains"}),
}
_GROUP_TYPES = frozenset(
    {"boolean", "char", "date", "datetime", "integer", "many2one", "selection"}
)
_AGGREGATES = {
    "count": None,
    "sum": frozenset({"float", "integer", "monetary"}),
    "min": frozenset({"date", "datetime", "float", "integer", "monetary"}),
    "max": frozenset({"date", "datetime", "float", "integer", "monetary"}),
}
_ODOO_OPERATOR = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "in": "in",
    "not_in": "not in",
    "contains": "ilike",
}

_SCHEMA_INPUT = {
    "type": "object",
    "properties": {"model": {"type": "string", "minLength": 1, "maxLength": 128}},
    "required": ["model"],
    "additionalProperties": False,
}
_SCHEMA_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "schema_id": {"type": "string"},
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
                    "sortable": {"type": "boolean"},
                    "groupable": {"type": "boolean"},
                    "operators": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "name",
                    "label",
                    "type",
                    "relation",
                    "sortable",
                    "groupable",
                    "operators",
                ],
                "additionalProperties": False,
            },
        },
        "captured_at": {"type": "string"},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": ["model", "schema_id", "fields", "captured_at", "content_trust"],
    "additionalProperties": False,
}
_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "match": {"type": "string", "enum": ["all", "any"]},
        "conditions": {
            "type": "array",
            "maxItems": _MAX_CONDITIONS,
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "operator": {"type": "string"},
                    "value": {},
                },
                "required": ["field", "operator", "value"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["match", "conditions"],
    "additionalProperties": False,
}
_QUERY_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "schema_id": {"type": "string", "minLength": 71, "maxLength": 71},
        "fields": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_FIELDS,
            "items": {"type": "string"},
        },
        "filter": _FILTER_SCHEMA,
        "order": {
            "type": "array",
            "maxItems": _MAX_SORTS,
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
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_RECORDS},
    },
    "required": ["model", "schema_id", "fields"],
    "additionalProperties": False,
}
_QUERY_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "schema_id": {"type": "string"},
        "records": {
            "type": "array",
            "maxItems": _MAX_RECORDS,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "fields": {"type": "object"},
                },
                "required": ["id", "fields"],
                "additionalProperties": False,
            },
        },
        "returned_count": {"type": "integer"},
        "limit": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "captured_at": {"type": "string"},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": [
        "model",
        "schema_id",
        "records",
        "returned_count",
        "limit",
        "truncated",
        "captured_at",
        "content_trust",
    ],
    "additionalProperties": False,
}
_AGGREGATE_INPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "schema_id": {"type": "string", "minLength": 71, "maxLength": 71},
        "filter": _FILTER_SCHEMA,
        "metrics": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_METRICS,
            "items": {
                "type": "object",
                "description": (
                    "For count, field must be null. For sum, min or max, field must be "
                    "the name of an eligible schema field."
                ),
                "properties": {
                    "operation": {"type": "string", "enum": list(_AGGREGATES)},
                    "field": {
                        "type": ["string", "null"],
                        "description": (
                            "Use null exactly when operation is count; otherwise provide a "
                            "field name from the checked schema."
                        ),
                    },
                },
                "required": ["operation", "field"],
                "additionalProperties": False,
            },
        },
        "group_by": {
            "type": "array",
            "maxItems": _MAX_GROUP_BY,
            "items": {"type": "string"},
        },
        "group_limit": {"type": "integer", "minimum": 1, "maximum": _MAX_GROUPS},
    },
    "required": ["model", "schema_id", "metrics"],
    "additionalProperties": False,
}
_AGGREGATE_OUTPUT = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "schema_id": {"type": "string"},
        "groups": {
            "type": "array",
            "maxItems": _MAX_GROUPS,
            "items": {
                "type": "object",
                "properties": {
                    "group": {"type": "object"},
                    "metrics": {"type": "array", "maxItems": _MAX_METRICS},
                },
                "required": ["group", "metrics"],
                "additionalProperties": False,
            },
        },
        "returned_group_count": {"type": "integer"},
        "group_limit": {"type": "integer"},
        "truncated": {"type": "boolean"},
        "captured_at": {"type": "string"},
        "content_trust": {"type": "string", "enum": ["untrusted"]},
    },
    "required": [
        "model",
        "schema_id",
        "groups",
        "returned_group_count",
        "group_limit",
        "truncated",
        "captured_at",
        "content_trust",
    ],
    "additionalProperties": False,
}


@tool(
    name="odoo.search_models",
    title="Search Odoo models",
    description=(
        "Search the installed Odoo model registry under the effective user. Use this "
        "before guessing model names; discovery itself grants no record authority."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 32},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "models": {
                "type": "array",
                "maxItems": 32,
                "items": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["model", "label"],
                    "additionalProperties": False,
                },
            },
            "captured_at": {"type": "string"},
            "content_trust": {"type": "string", "enum": ["untrusted"]},
        },
        "required": ["models", "captured_at", "content_trust"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "discovery"),
    max_calls=8,
    max_input_bytes=2 * 1024,
    max_output_bytes=32 * 1024,
)
def search_models(context: CapabilityContext, arguments):
    try:
        models = search_agent_models(
            context.env,
            arguments["query"],
            limit=arguments.get("limit", 20),
        )
    except TurnContextError as error:
        raise CapabilityError(error.code) from error
    return CapabilityResult(
        data={
            "models": models,
            "captured_at": _now(),
            "content_trust": "untrusted",
        },
        changes_preconditions=bool(models),
    )


@tool(
    name="odoo.get_effective_schema",
    title="Inspect Odoo query schema",
    description=(
        "Return the current user-visible, bounded query schema for one eligible Odoo "
        "business model. Use its exact schema_id for subsequent reads."
    ),
    input_schema=_SCHEMA_INPUT,
    output_schema=_SCHEMA_OUTPUT,
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "schema"),
    max_calls=12,
    max_input_bytes=2 * 1024,
    max_output_bytes=96 * 1024,
)
def get_effective_schema(context: CapabilityContext, arguments):
    schema = _effective_schema(context, arguments.get("model"))
    return {**schema, "captured_at": _now(), "content_trust": "untrusted"}


@tool(
    name="odoo.query_records",
    title="Query Odoo records",
    description=(
        "Search and read bounded Odoo records under the effective user's ACLs, record "
        "rules, field access and active-company context using a previously checked schema."
    ),
    input_schema=_QUERY_INPUT,
    output_schema=_QUERY_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "records"),
    max_calls=12,
    max_input_bytes=16 * 1024,
    max_output_bytes=128 * 1024,
)
def query_records(context: CapabilityContext, arguments):
    schema = _effective_schema(context, arguments.get("model"))
    _require_schema_id(arguments.get("schema_id"), schema["schema_id"])
    fields = _field_list(arguments.get("fields"), minimum=1, maximum=_MAX_FIELDS)
    metadata = {item["name"]: item for item in schema["fields"]}
    if any(field not in metadata for field in fields):
        raise CapabilityError("field_not_in_schema")
    domain = _domain(arguments.get("filter"), metadata)
    order = _order(arguments.get("order"), metadata)
    limit = _bounded_int(arguments.get("limit", 20), 1, _MAX_RECORDS)
    model_set = _model_set(context, schema["model"])
    try:
        model_set.browse().check_access("read")
        records = model_set.search(domain, order=order, limit=limit + 1)
        truncated = len(records) > limit
        records = records[:limit]
        rows = records.read(list(fields), load=None)
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    except ValueError:
        raise CapabilityError("invalid_query") from None
    rows_by_id = {row.get("id"): row for row in rows}
    if len(rows_by_id) != len(rows) or set(rows_by_id) != set(records.ids):
        raise CapabilityError("access_denied")
    normalized = [
        {
            "id": record.id,
            "fields": {
                field: _normalize(rows_by_id[record.id].get(field)) for field in fields
            },
        }
        for record in records
    ]
    return {
        "model": schema["model"],
        "schema_id": schema["schema_id"],
        "records": normalized,
        "returned_count": len(normalized),
        "limit": limit,
        "truncated": truncated,
        "captured_at": _now(),
        "content_trust": "untrusted",
    }


@tool(
    name="odoo.aggregate_records",
    title="Aggregate Odoo records",
    description=(
        "Run bounded count, sum, min or max aggregation under the effective Odoo user. "
        'A count metric must be {"operation":"count","field":null}; sum, min and max '
        "require an eligible field name. Grouping is restricted to fields declared "
        "groupable by the checked schema."
    ),
    input_schema=_AGGREGATE_INPUT,
    output_schema=_AGGREGATE_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "aggregate"),
    max_calls=12,
    max_input_bytes=16 * 1024,
    max_output_bytes=128 * 1024,
)
def aggregate_records(context: CapabilityContext, arguments):
    schema = _effective_schema(context, arguments.get("model"))
    _require_schema_id(arguments.get("schema_id"), schema["schema_id"])
    metadata = {item["name"]: item for item in schema["fields"]}
    domain = _domain(arguments.get("filter"), metadata)
    group_by = _field_list(arguments.get("group_by", []), minimum=0, maximum=_MAX_GROUP_BY)
    if any(field not in metadata or not metadata[field]["groupable"] for field in group_by):
        raise CapabilityError("field_not_groupable")
    metrics = _metrics(arguments.get("metrics"), metadata)
    group_limit = _bounded_int(arguments.get("group_limit", 20), 1, _MAX_GROUPS)
    model_set = _model_set(context, schema["model"])
    aggregate_specs = [
        f"ai_metric_{index}:{operation}({field or 'id'})"
        for index, (operation, field) in enumerate(metrics)
    ]
    try:
        model_set.browse().check_access("read")
        rows = model_set.read_group(
            domain,
            [*group_by, *aggregate_specs],
            group_by,
            limit=group_limit + 1 if group_by else 1,
            lazy=False,
        )
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    except ValueError:
        raise CapabilityError("invalid_query") from None
    truncated = bool(group_by) and len(rows) > group_limit
    rows = rows[:group_limit]
    groups = []
    for row in rows:
        groups.append(
            {
                "group": {field: _normalize(row.get(field)) for field in group_by},
                "metrics": [
                    {
                        "operation": operation,
                        "field": field,
                        "value": _normalize(row.get(f"ai_metric_{index}")),
                    }
                    for index, (operation, field) in enumerate(metrics)
                ],
            }
        )
    return {
        "model": schema["model"],
        "schema_id": schema["schema_id"],
        "groups": groups,
        "returned_group_count": len(groups),
        "group_limit": group_limit,
        "truncated": truncated,
        "captured_at": _now(),
        "content_trust": "untrusted",
    }


def _effective_schema(context: CapabilityContext, raw_model):
    model = _model_name(raw_model)
    model_set = _model_set(context, model)
    try:
        model_set.browse().check_access("read")
        allowed = visible_query_fields(context.env, model)
        descriptions = model_set.fields_get(
            allfields=list(allowed),
            attributes=["string", "type", "relation", "store", "sortable"],
        )
    except TurnContextError as error:
        raise CapabilityError(error.code) from error
    except (AccessError, MissingError, ValidationError, KeyError):
        raise CapabilityError("access_denied") from None
    if not isinstance(descriptions, dict):
        raise CapabilityError("schema_unavailable")
    fields = []
    for name in allowed:
        description = descriptions.get(name)
        if not isinstance(description, dict):
            continue
        field_type = description.get("type")
        if field_type not in _FILTER_OPERATORS:
            continue
        stored = description.get("store") is True or name == "id"
        sortable = description.get("sortable") is not False and stored
        fields.append(
            {
                "name": name,
                "label": _label(description.get("string"), name),
                "type": field_type,
                "relation": (
                    description.get("relation")
                    if isinstance(description.get("relation"), str)
                    else ""
                ),
                "sortable": sortable,
                "groupable": stored and field_type in _GROUP_TYPES,
                "operators": sorted(_FILTER_OPERATORS[field_type]),
            }
        )
    if not fields:
        raise CapabilityError("schema_unavailable")
    canonical = json.dumps(
        {"model": model, "fields": fields},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "model": model,
        "schema_id": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "fields": fields,
    }


def _model_set(context, model):
    if not agent_model_is_eligible(context.env, model):
        raise CapabilityError("query_model_not_allowed")
    try:
        return context.env[model]
    except KeyError:
        raise CapabilityError("query_model_not_allowed") from None


def _domain(raw, metadata):
    if raw is None:
        raw = {"match": "all", "conditions": []}
    if not isinstance(raw, dict) or set(raw) != {"match", "conditions"}:
        raise CapabilityError("invalid_query")
    match = raw.get("match")
    conditions = raw.get("conditions")
    if match not in {"all", "any"} or not isinstance(conditions, list) or len(conditions) > _MAX_CONDITIONS:
        raise CapabilityError("invalid_query")
    leaves = []
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) != {"field", "operator", "value"}:
            raise CapabilityError("invalid_query")
        field = _field_name(condition["field"])
        item = metadata.get(field)
        operator = condition["operator"]
        if item is None or not isinstance(operator, str) or operator not in item["operators"]:
            raise CapabilityError("operator_not_allowed")
        value = _query_value(condition["value"], item["type"], operator)
        leaves.append((field, _ODOO_OPERATOR[operator], value))
    if match == "any" and len(leaves) > 1:
        return ["|"] * (len(leaves) - 1) + leaves
    return leaves


def _order(raw, metadata):
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) > _MAX_SORTS:
        raise CapabilityError("invalid_query")
    result = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"field", "direction"}:
            raise CapabilityError("invalid_query")
        field = _field_name(item["field"])
        direction = item["direction"]
        if field in seen or direction not in {"asc", "desc"}:
            raise CapabilityError("invalid_query")
        if field not in metadata or not metadata[field]["sortable"]:
            raise CapabilityError("field_not_sortable")
        seen.add(field)
        result.append(f"{field} {direction}")
    return ", ".join(result) if result else None


def _metrics(raw, metadata):
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_METRICS:
        raise CapabilityError("invalid_query")
    result = []
    seen = set()
    for metric in raw:
        if not isinstance(metric, dict) or set(metric) != {"operation", "field"}:
            raise CapabilityError("invalid_query")
        operation = metric["operation"]
        field = metric["field"]
        if operation not in _AGGREGATES:
            raise CapabilityError("aggregate_not_allowed")
        if operation == "count":
            if field is not None:
                raise CapabilityError("invalid_query")
            normalized_field = None
        else:
            normalized_field = _field_name(field)
            item = metadata.get(normalized_field)
            allowed_types = _AGGREGATES[operation]
            if item is None or allowed_types is None or item["type"] not in allowed_types:
                raise CapabilityError("aggregate_not_allowed")
        identity = (operation, normalized_field)
        if identity in seen:
            raise CapabilityError("invalid_query")
        seen.add(identity)
        result.append(identity)
    return result


def _query_value(value, field_type, operator):
    list_operator = operator in {"in", "not_in"}
    if list_operator:
        if not isinstance(value, list) or not 1 <= len(value) <= 32:
            raise CapabilityError("query_value_invalid")
        return [_scalar_query_value(item, field_type) for item in value]
    return _scalar_query_value(value, field_type)


def _scalar_query_value(value, field_type):
    if value is None:
        return False
    if field_type == "boolean":
        if type(value) is not bool:
            raise CapabilityError("query_value_invalid")
        return value
    if field_type in {"integer", "many2one"}:
        if type(value) is not int:
            raise CapabilityError("query_value_invalid")
        return value
    if field_type in {"float", "monetary"}:
        if type(value) not in {int, float}:
            raise CapabilityError("query_value_invalid")
        return value
    if field_type in {"char", "text", "html", "selection", "date", "datetime"}:
        if not isinstance(value, str) or len(value) > 1_024 or "\x00" in value:
            raise CapabilityError("query_value_invalid")
        return value
    raise CapabilityError("query_value_invalid")


def _require_schema_id(raw, expected):
    if not isinstance(raw, str) or not _SCHEMA_ID.fullmatch(raw) or raw != expected:
        raise CapabilityError("schema_mismatch")


def _model_name(value):
    if not isinstance(value, str) or not _MODEL.fullmatch(value):
        raise CapabilityError("query_model_not_allowed")
    return value


def _field_name(value):
    if not isinstance(value, str) or not _FIELD.fullmatch(value):
        raise CapabilityError("invalid_query")
    return value


def _field_list(value, *, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise CapabilityError("invalid_query")
    fields = [_field_name(item) for item in value]
    if len(fields) != len(set(fields)):
        raise CapabilityError("invalid_query")
    return fields


def _bounded_int(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CapabilityError("invalid_query")
    return value


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


def _now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
