"""Validate b1 and execute exact batch chunks idempotently under the real Odoo user."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol
from uuid import UUID

from odoo import api
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.registry import Registry

from ..security.batch_authority import (
    BatchAuthorityCodec,
    BatchAuthorityPayload,
)
from ..security.delegation import DelegationTokenError
from .action_tools import (
    _BLOCKED_FIELDS,
    _BLOCKED_MODELS,
    _BLOCKED_MODEL_PREFIXES,
    _SENSITIVE_FIELD_PARTS,
    _VALUE_KIND_BY_FIELD_TYPE,
    _orm_write_value,
)
from .batch_tools import (
    ATOMIC_CHUNK,
    execute_create_chunk,
    execute_delete_chunk,
    execute_uniform_patch_chunk,
)
from .orm_tools import OrmToolError

MAX_BATCH_ROWS: Final = 200
MAX_ACTION_FIELDS: Final = 16
MAX_ACTION_VALUE_TEXT: Final = 4_000
_DECIMAL_PATTERN: Final = __import__("re").compile(
    r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,6})?$"
)
_DATE_PATTERN: Final = __import__("re").compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATETIME_PATTERN: Final = __import__("re").compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


class BatchEnvironmentProvider(Protocol):
    def __call__(self, claims: BatchAuthorityPayload) -> AbstractContextManager[object]: ...


class ApprovedBatchMutationExecutor:
    """Commit exactly one signed chunk; receipts make retransmission idempotent."""

    def __init__(
        self,
        *,
        codec: BatchAuthorityCodec,
        environment_provider: BatchEnvironmentProvider | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_batch_environment

    def commit(self, *, authority_token: str, batch: object) -> dict[str, object]:
        parsed = _batch(batch)
        try:
            claims = self._codec.decode(authority_token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        _require_authority(parsed, claims)
        try:
            with self._environment_provider(claims) as env:
                _validate_runtime_fields(env, parsed, claims)
                results = _execute_with_receipts(env, parsed, claims)
        except OrmToolError:
            raise
        except (AccessError, MissingError):
            raise OrmToolError("access_denied", 403) from None
        except ValidationError:
            raise OrmToolError("business_rule_rejected", 409) from None
        return {
            "attempt_id": str(claims.attempt_id),
            "chunk_fingerprint": claims.chunk_fingerprint,
            "job_id": str(claims.job_id),
            "ok": True,
            "results": list(results),
        }


def _execute_with_receipts(env, batch: dict[str, object], claims: BatchAuthorityPayload):
    receipt_model = env["odoo.ai.batch.execution"]
    new_rows = []
    results_by_ref: dict[str, dict[str, object]] = {}
    receipts_by_ref = {}
    for item in batch["items"]:
        item_fingerprint = _item_fingerprint(item)
        receipt, is_new = receipt_model._claim(
            job_id=claims.job_id,
            attempt_id=claims.attempt_id,
            authorization_id=claims.authorization_id,
            job_fingerprint=claims.job_fingerprint,
            operation=claims.operation,
            target_model=claims.model,
            source_ref=item["source_ref"],
            item_fingerprint=item_fingerprint,
        )
        receipt = receipt._internal()
        if is_new:
            new_rows.append(item)
            receipts_by_ref[item["source_ref"]] = receipt
            continue
        try:
            results_by_ref[item["source_ref"]] = receipt._result()
        except ValidationError:
            raise OrmToolError("execution_in_progress", 409) from None

    if batch["failure_mode"] == ATOMIC_CHUNK and results_by_ref and new_rows:
        raise OrmToolError("batch_atomic_resume_mismatch", 409)

    if new_rows:
        if batch["operation"] == "create":
            raw_results = execute_create_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (
                        item["source_ref"],
                        _orm_values(item["values"]),
                    )
                    for item in new_rows
                ),
                failure_mode=batch["failure_mode"],
            )
        elif batch["operation"] == "patch":
            signatures = {
                _canonical_json(item["changes"])
                for item in new_rows
            }
            if len(signatures) != 1:
                raise OrmToolError("batch_patch_not_uniform", 422)
            raw_results = execute_uniform_patch_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (item["source_ref"], item["record_id"])
                    for item in new_rows
                ),
                values=_orm_values(new_rows[0]["changes"]),
                failure_mode=batch["failure_mode"],
            )
        else:
            raw_results = execute_delete_chunk(
                env,
                model=batch["model"],
                rows=tuple(
                    (item["source_ref"], item["record_id"])
                    for item in new_rows
                ),
                failure_mode=batch["failure_mode"],
            )
        for result in raw_results:
            receipt = receipts_by_ref[result["source_ref"]]
            if result["state"] == "applied":
                receipt._complete_applied(record_id=result["record_id"])
            else:
                receipt._complete_failed(error_code=result["error_code"])
            results_by_ref[result["source_ref"]] = receipt._result()

    ordered = tuple(results_by_ref[item["source_ref"]] for item in batch["items"])
    if len(ordered) != len(batch["items"]):
        raise OrmToolError("invalid_batch_result", 502)
    return ordered


def _validate_runtime_fields(env, batch: dict[str, object], claims: BatchAuthorityPayload) -> None:
    model = batch["model"]
    if model in _BLOCKED_MODELS or any(model.startswith(prefix) for prefix in _BLOCKED_MODEL_PREFIXES):
        raise OrmToolError("action_target_not_allowed", 403)
    model_set = env[model]
    if batch["operation"] == "delete":
        model_set.browse().check_access("unlink")
        return
    fields = claims.fields
    if not fields:
        raise OrmToolError("scope_denied", 403)
    model_set.check_field_access_rights("write", list(fields))
    if batch["operation"] == "create":
        model_set.browse().check_access("create")
    else:
        model_set.browse().check_access("write")
    descriptions = model_set.fields_get(
        list(fields),
        attributes=["type", "readonly", "required", "relation", "selection"],
    )
    if not isinstance(descriptions, dict) or set(descriptions) != set(fields):
        raise OrmToolError("field_not_allowed", 403)
    for field in fields:
        if (
            field in _BLOCKED_FIELDS
            or any(part in field.lower() for part in _SENSITIVE_FIELD_PARTS)
        ):
            raise OrmToolError("field_not_allowed", 403)
        description = descriptions[field]
        expected_kind = _VALUE_KIND_BY_FIELD_TYPE.get(description.get("type"))
        if expected_kind is None or description.get("readonly") is not False:
            raise OrmToolError("field_not_allowed", 403)
        for tagged in _values_for_field(batch["items"], field):
            if tagged["kind"] != expected_kind:
                raise OrmToolError("write_schema_mismatch", 409)
            value = tagged["value"]
            if description.get("required") is True and (
                value is None or expected_kind == "text" and value == ""
            ):
                raise OrmToolError("invalid_action", 422)
            if expected_kind == "selection" and value is not None:
                options = description.get("selection") or []
                allowed = {
                    option[0]
                    for option in options
                    if isinstance(option, (list, tuple))
                    and len(option) == 2
                    and isinstance(option[0], str)
                }
                if value not in allowed:
                    raise OrmToolError("invalid_action", 422)
            if expected_kind == "many2one" and value is not None:
                relation = description.get("relation")
                if not isinstance(relation, str):
                    raise OrmToolError("field_not_allowed", 403)
                related = env[relation].browse([value])
                related.check_access("read")
                if len(related.exists()) != 1:
                    raise OrmToolError("access_denied", 403)


def _values_for_field(items, field):
    values = []
    for item in items:
        assignments = item.get("values") if item["operation"] == "create" else item.get("changes", [])
        for assignment in assignments:
            if assignment["field"] == field:
                values.append(assignment["value"])
    return values


def _batch(value: object) -> dict[str, object]:
    raw = _exact_dict(
        value,
        {"operation", "model", "schema_id", "failure_mode", "items"},
    )
    operation = raw["operation"]
    if operation not in {"create", "patch", "delete"}:
        raise OrmToolError("invalid_request", 422)
    model = raw["model"]
    if not isinstance(model, str) or not 1 <= len(model) <= 128:
        raise OrmToolError("invalid_request", 422)
    failure_mode = raw["failure_mode"]
    if failure_mode not in {"continue_on_error", "atomic_chunk"}:
        raise OrmToolError("invalid_request", 422)
    schema_id = raw["schema_id"]
    if operation in {"create", "patch"}:
        if not isinstance(schema_id, str) or not 1 <= len(schema_id) <= 128:
            raise OrmToolError("invalid_request", 422)
    elif schema_id is not None:
        raise OrmToolError("invalid_request", 422)
    items = raw["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH_ROWS:
        raise OrmToolError("invalid_request", 422)
    parsed_items = [_batch_item(item, operation) for item in items]
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


def _batch_item(value: object, operation: str) -> dict[str, object]:
    if operation == "create":
        raw = _exact_dict(value, {"operation", "source_ref", "values"})
        assignments_name = "values"
    elif operation == "patch":
        raw = _exact_dict(value, {"operation", "source_ref", "record_id", "changes"})
        assignments_name = "changes"
    else:
        raw = _exact_dict(value, {"operation", "source_ref", "record_id"})
        assignments_name = None
    if raw["operation"] != operation or not _source_ref(raw["source_ref"]):
        raise OrmToolError("invalid_request", 422)
    if operation != "create" and (
        type(raw["record_id"]) is not int or raw["record_id"] <= 0
    ):
        raise OrmToolError("invalid_request", 422)
    result = dict(raw)
    if assignments_name is not None:
        assignments = raw[assignments_name]
        if not isinstance(assignments, list) or not 1 <= len(assignments) <= MAX_ACTION_FIELDS:
            raise OrmToolError("invalid_request", 422)
        parsed = [_assignment(item) for item in assignments]
        fields = tuple(item["field"] for item in parsed)
        if len(fields) != len(set(fields)):
            raise OrmToolError("invalid_request", 422)
        result[assignments_name] = parsed
    return result


def _assignment(value: object) -> dict[str, object]:
    raw = _exact_dict(value, {"field", "value"})
    field = raw["field"]
    if (
        not isinstance(field, str)
        or not 1 <= len(field) <= 128
        or not (field[0].isalpha() or field[0] == "_")
        or any(not (character.isalnum() or character == "_") for character in field)
    ):
        raise OrmToolError("invalid_request", 422)
    return {"field": field, "value": _tagged_value(raw["value"])}


def _tagged_value(value: object) -> dict[str, object]:
    raw = _exact_dict(value, {"kind", "value"})
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
    if not isinstance(item, str) or len(item) > MAX_ACTION_VALUE_TEXT:
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


def _orm_values(assignments) -> dict[str, object]:
    return {
        assignment["field"]: _orm_write_value(assignment["value"])
        for assignment in assignments
    }


def _require_authority(batch: dict[str, object], claims: BatchAuthorityPayload) -> None:
    fields = sorted(
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
    fingerprint = _chunk_fingerprint(batch)
    if (
        claims.scopes != ("batch_commit",)
        or claims.operation != batch["operation"]
        or claims.model != batch["model"]
        or claims.schema_id != batch["schema_id"]
        or claims.fields != tuple(fields)
        or claims.failure_mode != batch["failure_mode"]
        or claims.row_count != len(batch["items"])
        or not hmac.compare_digest(claims.chunk_fingerprint, fingerprint)
    ):
        raise OrmToolError("scope_denied", 403)


def _chunk_fingerprint(batch: dict[str, object]) -> str:
    payload = {
        "failure_mode": batch["failure_mode"],
        "items": batch["items"],
        "model": batch["model"],
        "operation": batch["operation"],
        "schema_id": batch["schema_id"],
    }
    return "batch-chunk:v1:sha256:" + hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _item_fingerprint(item: dict[str, object]) -> str:
    return "batch-item:v1:sha256:" + hashlib.sha256(
        _canonical_json(item).encode("utf-8")
    ).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _exact_dict(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys or any(
        not isinstance(key, str) for key in value
    ):
        raise OrmToolError("invalid_request", 422)
    return value


def _source_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )


@contextmanager
def _runtime_batch_environment(claims: BatchAuthorityPayload):
    registry = Registry(claims.database)
    with registry.cursor() as cursor:
        environment = api.Environment(
            cursor,
            claims.uid,
            {
                "allowed_company_ids": list(claims.allowed_company_ids),
                "company_id": claims.company_id,
            },
        )
        yield environment
