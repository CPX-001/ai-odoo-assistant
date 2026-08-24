"""Shared structural parser for effect-free preflight and signed batch commit.

This module validates only the provider-neutral normalized batch wire shape. Runtime
Odoo ACL, record rules, field metadata and relations remain executor responsibilities.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from .action_tools import _VALUE_KIND_BY_FIELD_TYPE
from .orm_tools import OrmToolError

MAX_BATCH_ROWS: Final = 200
MAX_BATCH_FIELDS: Final = 64
MAX_BATCH_SOURCE_REF: Final = 128
MAX_BATCH_VALUE_TEXT: Final = 4_000
_DECIMAL_PATTERN: Final = re.compile(
    r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,6})?$"
)
_DATE_PATTERN: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATETIME_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


def parse_batch(value: object, *, max_rows: int = MAX_BATCH_ROWS) -> dict[str, object]:
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_BATCH_ROWS:
        raise OrmToolError("invalid_request", 422)
    raw = exact_dict(
        value,
        {"operation", "model", "schema_id", "failure_mode", "items"},
    )
    operation = raw["operation"]
    if operation not in {"create", "patch", "delete"}:
        raise OrmToolError("invalid_request", 422)
    model = raw["model"]
    if not isinstance(model, str) or re.fullmatch(
        r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$", model
    ) is None:
        raise OrmToolError("invalid_request", 422)
    failure_mode = raw["failure_mode"]
    if failure_mode not in {"continue_on_error", "atomic_chunk"}:
        raise OrmToolError("invalid_request", 422)
    schema_id = raw["schema_id"]
    if operation in {"create", "patch"}:
        if (
            not isinstance(schema_id, str)
            or re.fullmatch(
                r"^[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}$",
                schema_id,
            )
            is None
        ):
            raise OrmToolError("invalid_request", 422)
    elif schema_id is not None:
        raise OrmToolError("invalid_request", 422)
    items = raw["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= max_rows:
        raise OrmToolError("invalid_request", 422)
    parsed_items = [parse_batch_item(item, operation) for item in items]
    refs = tuple(item["source_ref"] for item in parsed_items)
    if len(refs) != len(set(refs)):
        raise OrmToolError("invalid_request", 422)
    if operation != "create":
        ids = tuple(item["record_id"] for item in parsed_items)
        if len(ids) != len(set(ids)):
            raise OrmToolError("invalid_request", 422)
    return {
        "operation": operation,
        "model": model,
        "schema_id": schema_id,
        "failure_mode": failure_mode,
        "items": parsed_items,
    }


def parse_batch_item(value: object, operation: str) -> dict[str, object]:
    if operation == "create":
        raw = exact_dict(value, {"operation", "source_ref", "values"})
        assignments_name = "values"
    elif operation == "patch":
        raw = exact_dict(value, {"operation", "source_ref", "record_id", "changes"})
        assignments_name = "changes"
    else:
        raw = exact_dict(value, {"operation", "source_ref", "record_id"})
        assignments_name = None
    if raw["operation"] != operation or not source_ref_valid(raw["source_ref"]):
        raise OrmToolError("invalid_request", 422)
    if operation != "create" and (
        type(raw["record_id"]) is not int or raw["record_id"] <= 0
    ):
        raise OrmToolError("invalid_request", 422)
    result = dict(raw)
    if assignments_name is not None:
        assignments = raw[assignments_name]
        if (
            not isinstance(assignments, list)
            or not 1 <= len(assignments) <= MAX_BATCH_FIELDS
        ):
            raise OrmToolError("invalid_request", 422)
        parsed = [parse_assignment(item) for item in assignments]
        fields = tuple(item["field"] for item in parsed)
        if len(fields) != len(set(fields)):
            raise OrmToolError("invalid_request", 422)
        result[assignments_name] = parsed
    return result


def parse_assignment(value: object) -> dict[str, object]:
    raw = exact_dict(value, {"field", "value"})
    field = raw["field"]
    if (
        not isinstance(field, str)
        or re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", field) is None
    ):
        raise OrmToolError("invalid_request", 422)
    return {"field": field, "value": parse_tagged_value(raw["value"])}


def parse_tagged_value(value: object) -> dict[str, object]:
    raw = exact_dict(value, {"kind", "value"})
    kind = raw["kind"]
    item = raw["value"]
    if kind not in frozenset(_VALUE_KIND_BY_FIELD_TYPE.values()):
        raise OrmToolError("invalid_request", 422)
    if item is None:
        return {"kind": kind, "value": None}
    if kind == "boolean" and type(item) is bool:
        return {"kind": kind, "value": item}
    if kind in {"integer", "many2one"}:
        if type(item) is not int or (kind == "many2one" and item <= 0):
            raise OrmToolError("invalid_request", 422)
        return {"kind": kind, "value": item}
    if not isinstance(item, str) or len(item) > MAX_BATCH_VALUE_TEXT:
        raise OrmToolError("invalid_request", 422)
    if kind == "decimal":
        if _DECIMAL_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_request", 422)
        try:
            decimal = Decimal(item)
        except InvalidOperation:
            raise OrmToolError("invalid_request", 422) from None
        normalized = format(decimal, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"", "-0"}:
            normalized = "0"
        if item != normalized:
            raise OrmToolError("invalid_request", 422)
    if kind == "date":
        if _DATE_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_request", 422)
        try:
            date.fromisoformat(item)
        except ValueError:
            raise OrmToolError("invalid_request", 422) from None
    if kind == "datetime":
        if _DATETIME_PATTERN.fullmatch(item) is None:
            raise OrmToolError("invalid_request", 422)
        try:
            datetime.fromisoformat(item.replace("Z", "+00:00"))
        except ValueError:
            raise OrmToolError("invalid_request", 422) from None
    if kind == "selection" and (not item or len(item) > 256):
        raise OrmToolError("invalid_request", 422)
    return {"kind": kind, "value": item}


def batch_fields(batch: dict[str, object]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                assignment["field"]
                for item in batch["items"]
                for assignment in (
                    item.get("values")
                    if item["operation"] == "create"
                    else item.get("changes", [])
                )
            }
        )
    )


def values_for_field(items, field: str) -> tuple[dict[str, object], ...]:
    values = []
    for item in items:
        assignments = (
            item.get("values")
            if item["operation"] == "create"
            else item.get("changes", [])
        )
        for assignment in assignments:
            if assignment["field"] == field:
                values.append(assignment["value"])
    return tuple(values)


def chunk_fingerprint(batch: dict[str, object]) -> str:
    payload = {
        "failure_mode": batch["failure_mode"],
        "items": batch["items"],
        "model": batch["model"],
        "operation": batch["operation"],
        "schema_id": batch["schema_id"],
    }
    return "batch-chunk:v1:sha256:" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()


def item_fingerprint(item: dict[str, object]) -> str:
    return "batch-item:v1:sha256:" + hashlib.sha256(
        canonical_json(item).encode("utf-8")
    ).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def exact_dict(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys or any(
        not isinstance(key, str) for key in value
    ):
        raise OrmToolError("invalid_request", 422)
    return value


def source_ref_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= MAX_BATCH_SOURCE_REF
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )
