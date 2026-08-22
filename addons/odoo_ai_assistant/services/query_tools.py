"""Narrow structured QUERY execution under separately delegated Odoo authority."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from typing import Final, Protocol
from uuid import UUID

from odoo import api
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.registry import Registry

from ..security import (
    DelegationTokenError,
    QueryDelegationCodec,
    QueryDelegationPayload,
)
from .orm_tools import (
    JsonValue,
    OrmToolError,
    check_response_size,
    collect_model_metadata,
    iso_datetime,
    normalize_orm_value,
)

MAX_QUERY_RECORDS: Final = 50
MAX_QUERY_FIELDS: Final = 16
MAX_QUERY_CONDITIONS: Final = 8
MAX_QUERY_SORTS: Final = 3
MAX_QUERY_GROUPS: Final = 50
MAX_QUERY_GROUP_BY: Final = 2
MAX_QUERY_AGGREGATES: Final = 8
MAX_QUERY_LIST_VALUES: Final = 32
MAX_QUERY_STRING_VALUE: Final = 1_024
QUERY_POLICY_REVISION: Final = "m5-query-read-v1"

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_OPERATORS: Final = {
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
_ORDER_DIRECTIONS: Final = {"asc": "asc", "desc": "desc"}
_FILTER_OPERATORS_BY_TYPE: Final = {
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
_READ_TYPES: Final = frozenset(_FILTER_OPERATORS_BY_TYPE)
_GROUP_TYPES: Final = frozenset(
    {"boolean", "char", "date", "datetime", "integer", "many2one", "selection"}
)
_SUM_TYPES: Final = frozenset({"float", "integer", "monetary"})
_MIN_MAX_TYPES: Final = frozenset({"date", "datetime", "float", "integer", "monetary"})


class QueryEnvironmentProvider(Protocol):
    def __call__(
        self, claims: QueryDelegationPayload
    ) -> AbstractContextManager[object]: ...


class QueryReplayGuard(Protocol):
    def __call__(self, claims: QueryDelegationPayload, scope: str) -> None: ...


class DelegatedQueryToolExecutor:
    """Decode q1 authority and translate only validated AST nodes into ORM calls."""

    def __init__(
        self,
        *,
        codec: QueryDelegationCodec,
        environment_provider: QueryEnvironmentProvider | None = None,
        replay_guard: QueryReplayGuard | None = None,
        observed_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_query_environment
        self._replay_guard = replay_guard or _runtime_query_replay_guard
        self._observed_at = observed_at or _utc_now

    def get_model_metadata(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        model: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        parsed_model = _model_name(model)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="query_schema",
            model=parsed_model,
        )
        self._replay_guard(claims, "query_schema")
        try:
            with self._environment_provider(claims) as env:
                return collect_model_metadata(
                    env,
                    model=parsed_model,
                    max_fields=len(claims.allowed_fields),
                    observed_at=self._observed_at(),
                    allowed_fields=frozenset(claims.allowed_fields),
                )
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None

    def query_records(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        payload: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        request = _query_request(payload)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="query_records",
            model=request["model"],
        )
        _check_record_authority(request, claims)
        self._replay_guard(claims, "query_records")
        try:
            with self._environment_provider(claims) as env:
                model_set = env[request["model"]]
                domain = _domain(model_set, request["filter"], claims)
                fields = _read_fields(model_set, request["fields"], claims)
                order = _order(model_set, request["order"], claims)
                model_set.browse().check_access("read")
                records = model_set.search(
                    domain,
                    order=order,
                    limit=request["limit"] + 1,
                )
                truncated = len(records) > request["limit"]
                records = records[: request["limit"]]
                rows = records.read(list(fields), load=None)
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None
        except ValueError:
            raise OrmToolError("invalid_query", 400) from None

        rows_by_id = {row.get("id"): row for row in rows}
        if len(rows_by_id) != len(rows) or set(rows_by_id) != set(records.ids):
            raise OrmToolError("access_denied", 403)
        normalized: list[JsonValue] = []
        for record in records:
            row = rows_by_id[record.id]
            normalized.append(
                {
                    "fields": {
                        name: normalize_orm_value(row.get(name)) for name in fields
                    },
                    "id": record.id,
                }
            )
        result: dict[str, JsonValue] = {
            "captured_at": iso_datetime(self._observed_at()),
            "limit": request["limit"],
            "model": request["model"],
            "ok": True,
            "records": normalized,
            "returned_count": len(normalized),
            "truncated": truncated,
        }
        check_response_size(result)
        return result

    def aggregate_records(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        payload: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        request = _aggregate_request(payload)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="aggregate_records",
            model=request["model"],
        )
        _check_aggregate_authority(request, claims)
        self._replay_guard(claims, "aggregate_records")
        try:
            with self._environment_provider(claims) as env:
                model_set = env[request["model"]]
                domain = _domain(model_set, request["filter"], claims)
                group_by = _group_fields(model_set, request["group_by"], claims)
                metric_fields = _metric_specs(model_set, request["metrics"], claims)
                model_set.browse().check_access("read")
                raw_groups = model_set.read_group(
                    domain,
                    [*group_by, *metric_fields],
                    list(group_by),
                    limit=request["group_limit"] + 1 if group_by else 1,
                    lazy=False,
                )
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError, KeyError):
            raise OrmToolError("access_denied", 403) from None
        except ValueError:
            raise OrmToolError("invalid_query", 400) from None

        truncated = bool(group_by) and len(raw_groups) > request["group_limit"]
        raw_groups = raw_groups[: request["group_limit"]]
        groups = [
            _aggregate_group(row, group_by=group_by, metrics=request["metrics"])
            for row in raw_groups
        ]
        result: dict[str, JsonValue] = {
            "captured_at": iso_datetime(self._observed_at()),
            "group_limit": request["group_limit"],
            "groups": groups,
            "model": request["model"],
            "ok": True,
            "returned_group_count": len(groups),
            "truncated": truncated,
        }
        check_response_size(result)
        return result

    def _authorize(
        self,
        token: str,
        *,
        turn_id: UUID,
        scope: str,
        model: str,
    ) -> QueryDelegationPayload:
        try:
            claims = self._codec.decode(token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        if (
            claims.turn_id != turn_id
            or claims.model != model
            or scope not in claims.scopes
            or claims.policy_revision != QUERY_POLICY_REVISION
        ):
            raise OrmToolError("scope_denied", 403)
        return claims


def _query_request(value: object) -> dict[str, object]:
    raw = _exact_dict(value, {"fields", "filter", "limit", "model", "order"})
    model = _model_name(raw["model"])
    fields = _field_list(raw["fields"], minimum=1, maximum=MAX_QUERY_FIELDS)
    query_filter = _filter(raw["filter"])
    limit = _bounded_int(raw["limit"], minimum=1, maximum=MAX_QUERY_RECORDS)
    if not isinstance(raw["order"], list) or len(raw["order"]) > MAX_QUERY_SORTS:
        raise OrmToolError("invalid_query", 400)
    order: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw["order"]:
        sort = _exact_dict(item, {"direction", "field"})
        field = _field_name(sort["field"])
        direction = sort["direction"]
        if (
            field in seen
            or not isinstance(direction, str)
            or direction not in _ORDER_DIRECTIONS
        ):
            raise OrmToolError("invalid_query", 400)
        seen.add(field)
        order.append({"direction": direction, "field": field})
    return {
        "fields": fields,
        "filter": query_filter,
        "limit": limit,
        "model": model,
        "order": order,
    }


def _aggregate_request(value: object) -> dict[str, object]:
    raw = _exact_dict(
        value,
        {"filter", "group_by", "group_limit", "metrics", "model"},
    )
    model = _model_name(raw["model"])
    query_filter = _filter(raw["filter"])
    group_by = _field_list(raw["group_by"], minimum=0, maximum=MAX_QUERY_GROUP_BY)
    group_limit = _bounded_int(raw["group_limit"], minimum=1, maximum=MAX_QUERY_GROUPS)
    if (
        not isinstance(raw["metrics"], list)
        or not 1 <= len(raw["metrics"]) <= MAX_QUERY_AGGREGATES
    ):
        raise OrmToolError("invalid_query", 400)
    metrics: list[dict[str, str | None]] = []
    identities: set[tuple[str, str | None]] = set()
    for item in raw["metrics"]:
        metric = _exact_dict(item, {"field", "operation"})
        operation = metric["operation"]
        field_value = metric["field"]
        if not isinstance(operation, str) or operation not in {
            "count",
            "sum",
            "min",
            "max",
        }:
            raise OrmToolError("invalid_query", 400)
        if operation == "count":
            if field_value is not None:
                raise OrmToolError("invalid_query", 400)
            field = None
        else:
            field = _field_name(field_value)
        identity = (operation, field)
        if identity in identities:
            raise OrmToolError("invalid_query", 400)
        identities.add(identity)
        metrics.append({"field": field, "operation": operation})
    return {
        "filter": query_filter,
        "group_by": group_by,
        "group_limit": group_limit,
        "metrics": metrics,
        "model": model,
    }


def _filter(value: object) -> dict[str, object]:
    raw = _exact_dict(value, {"conditions", "match"})
    match = raw["match"]
    if match not in {"all", "any"} or not isinstance(raw["conditions"], list):
        raise OrmToolError("invalid_query", 400)
    if len(raw["conditions"]) > MAX_QUERY_CONDITIONS:
        raise OrmToolError("limit_exceeded", 413)
    conditions: list[dict[str, object]] = []
    for item in raw["conditions"]:
        condition = _exact_dict(item, {"field", "operator", "value"})
        operator = condition["operator"]
        if not isinstance(operator, str) or operator not in _OPERATORS:
            raise OrmToolError("invalid_query", 400)
        conditions.append(
            {
                "field": _field_name(condition["field"]),
                "operator": operator,
                "value": condition["value"],
            }
        )
    return {"conditions": conditions, "match": match}


def _domain(
    model_set: object, value: object, claims: QueryDelegationPayload
) -> list[object]:
    query_filter = value
    conditions = query_filter["conditions"]
    if len(conditions) > claims.max_conditions:
        raise OrmToolError("limit_exceeded", 413)
    domain: list[object] = []
    for condition in conditions:
        field_name = condition["field"]
        description = _runtime_field_description(model_set, field_name, claims)
        field_type = description["type"]
        operator = condition["operator"]
        if description[
            "searchable"
        ] is not True or operator not in _FILTER_OPERATORS_BY_TYPE.get(
            field_type, frozenset()
        ):
            raise OrmToolError("operator_not_allowed", 400)
        normalized = _condition_value(
            condition["value"], field_type=field_type, operator=operator
        )
        domain.append((field_name, _OPERATORS[operator], normalized))
    if query_filter["match"] == "any" and len(domain) > 1:
        return ["|"] * (len(domain) - 1) + domain
    return domain


def _read_fields(
    model_set: object, value: object, claims: QueryDelegationPayload
) -> tuple[str, ...]:
    fields = tuple(value)
    if len(fields) > claims.max_fields:
        raise OrmToolError("limit_exceeded", 413)
    for name in fields:
        description = _runtime_field_description(model_set, name, claims)
        if description["type"] not in _READ_TYPES:
            raise OrmToolError("field_not_allowed", 400)
    model_set.check_field_access_rights("read", list(fields))
    return fields


def _order(
    model_set: object, value: object, claims: QueryDelegationPayload
) -> str | None:
    terms: list[str] = []
    names: list[str] = []
    for item in value:
        name = item["field"]
        description = _runtime_field_description(model_set, name, claims)
        if (
            description["type"] not in _READ_TYPES
            or description["sortable"] is not True
        ):
            raise OrmToolError("field_not_sortable", 400)
        names.append(name)
        terms.append(f"{name} {_ORDER_DIRECTIONS[item['direction']]}")
    if names:
        model_set.check_field_access_rights("read", names)
    return ", ".join(terms) or None


def _group_fields(
    model_set: object, value: object, claims: QueryDelegationPayload
) -> tuple[str, ...]:
    names = tuple(value)
    for name in names:
        description = _runtime_field_description(model_set, name, claims)
        if (
            description["type"] not in _GROUP_TYPES
            or description["groupable"] is not True
        ):
            raise OrmToolError("field_not_groupable", 400)
    if names:
        model_set.check_field_access_rights("read", list(names))
    return names


def _metric_specs(
    model_set: object, value: object, claims: QueryDelegationPayload
) -> tuple[str, ...]:
    specs: list[str] = []
    checked: list[str] = []
    for index, metric in enumerate(value):
        operation = metric["operation"]
        field_name = metric["field"]
        if operation == "count":
            continue
        field = _runtime_field(model_set, field_name, claims)
        allowed_types = _SUM_TYPES if operation == "sum" else _MIN_MAX_TYPES
        if field.type not in allowed_types or not field.store:
            raise OrmToolError("aggregate_not_allowed", 400)
        checked.append(field_name)
        specs.append(f"metric_{index}:{operation}({field_name})")
    if checked:
        model_set.check_field_access_rights("read", checked)
    return tuple(specs)


def _aggregate_group(
    raw: object,
    *,
    group_by: tuple[str, ...],
    metrics: list[dict[str, str | None]],
) -> JsonValue:
    if not isinstance(raw, dict):
        raise OrmToolError("invalid_query_result", 500)
    group = {name: normalize_orm_value(raw.get(name)) for name in group_by}
    values: list[JsonValue] = []
    for index, metric in enumerate(metrics):
        operation = metric["operation"]
        key = "__count" if operation == "count" else f"metric_{index}"
        value = normalize_orm_value(raw.get(key))
        if operation == "count" and (type(value) is not int or value < 0):
            raise OrmToolError("invalid_query_result", 500)
        values.append(
            {
                "field": metric["field"],
                "operation": operation,
                "value": value,
            }
        )
    return {"group": group, "metrics": values}


def _condition_value(value: object, *, field_type: str, operator: str) -> object:
    if operator in {"in", "not_in"}:
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_QUERY_LIST_VALUES:
            raise OrmToolError("invalid_query_value", 400)
        return [
            _scalar_condition_value(item, field_type=field_type, allow_none=False)
            for item in value
        ]
    if operator == "contains":
        if not isinstance(value, str) or not 1 <= len(value) <= MAX_QUERY_STRING_VALUE:
            raise OrmToolError("invalid_query_value", 400)
        return value
    return _scalar_condition_value(
        value,
        field_type=field_type,
        allow_none=operator in {"eq", "ne"},
    )


def _scalar_condition_value(
    value: object, *, field_type: str, allow_none: bool
) -> object:
    if value is None:
        if not allow_none:
            raise OrmToolError("invalid_query_value", 400)
        return False
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise OrmToolError("invalid_query_value", 400)
        return value
    if field_type in {"integer", "many2one"}:
        if type(value) is not int or (field_type == "many2one" and value <= 0):
            raise OrmToolError("invalid_query_value", 400)
        return value
    if field_type in {"float", "monetary"}:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise OrmToolError("invalid_query_value", 400)
        return value
    if field_type in {"char", "html", "selection", "text"}:
        if not isinstance(value, str) or len(value) > MAX_QUERY_STRING_VALUE:
            raise OrmToolError("invalid_query_value", 400)
        return value
    if field_type == "date":
        if not isinstance(value, str):
            raise OrmToolError("invalid_query_value", 400)
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise OrmToolError("invalid_query_value", 400) from None
        if parsed.isoformat() != value:
            raise OrmToolError("invalid_query_value", 400)
        return value
    if field_type == "datetime":
        if not isinstance(value, str) or len(value) > 64:
            raise OrmToolError("invalid_query_value", 400)
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise OrmToolError("invalid_query_value", 400) from None
        return value
    raise OrmToolError("invalid_query_value", 400)


def _runtime_field(
    model_set: object, name: object, claims: QueryDelegationPayload
) -> object:
    if not isinstance(name, str) or name not in claims.allowed_fields:
        raise OrmToolError("field_not_allowed", 403)
    field = model_set._fields.get(name)
    if field is None:
        raise OrmToolError("field_not_allowed", 400)
    return field


def _runtime_field_description(
    model_set: object,
    name: object,
    claims: QueryDelegationPayload,
) -> dict[str, object]:
    _runtime_field(model_set, name, claims)
    descriptions = model_set.fields_get(
        allfields=[name],
        attributes=["type", "searchable", "sortable", "groupable"],
    )
    description = descriptions.get(name) if isinstance(descriptions, dict) else None
    if (
        not isinstance(description, dict)
        or not isinstance(description.get("type"), str)
        or not all(
            isinstance(description.get(attribute), bool)
            for attribute in ("searchable", "sortable", "groupable")
        )
    ):
        raise OrmToolError("field_not_allowed", 403)
    return description


def _check_record_authority(
    request: dict[str, object], claims: QueryDelegationPayload
) -> None:
    if (
        request["limit"] > claims.max_records
        or len(request["fields"]) > claims.max_fields
        or len(request["filter"]["conditions"]) > claims.max_conditions
    ):
        raise OrmToolError("limit_exceeded", 413)


def _check_aggregate_authority(
    request: dict[str, object], claims: QueryDelegationPayload
) -> None:
    if (
        request["group_limit"] > claims.max_groups
        or len(request["metrics"]) > claims.max_aggregates
        or len(request["filter"]["conditions"]) > claims.max_conditions
    ):
        raise OrmToolError("limit_exceeded", 413)


def _exact_dict(value: object, keys: set[str]) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or not all(isinstance(key, str) for key in value)
    ):
        raise OrmToolError("invalid_query", 400)
    return value


def _model_name(value: object) -> str:
    if not isinstance(value, str) or not _MODEL_PATTERN.fullmatch(value):
        raise OrmToolError("invalid_query", 400)
    return value


def _field_name(value: object) -> str:
    if not isinstance(value, str) or not _FIELD_PATTERN.fullmatch(value):
        raise OrmToolError("invalid_query", 400)
    return value


def _field_list(value: object, *, minimum: int, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise OrmToolError("invalid_query", 400)
    fields = tuple(_field_name(item) for item in value)
    if len(fields) != len(set(fields)):
        raise OrmToolError("invalid_query", 400)
    return fields


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise OrmToolError("limit_exceeded", 413)
    return value


def _turn_id(value: object) -> UUID:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise OrmToolError("invalid_query", 400) from None
    if str(parsed) != str(value):
        raise OrmToolError("invalid_query", 400)
    return parsed


@contextmanager
def _runtime_query_environment(claims: QueryDelegationPayload) -> Iterator[object]:
    context: dict[str, object] = {
        "allowed_company_ids": list(claims.allowed_company_ids)
    }
    if claims.lang is not None:
        context["lang"] = claims.lang
    try:
        database_registry = Registry(claims.database)
        with database_registry.cursor() as cursor:
            env = api.Environment(cursor, claims.uid, context, su=False)
            if env.su or env.cr.dbname != claims.database:
                raise OrmToolError("delegation_rejected", 403)
            if (
                env.company.id != claims.company_id
                or tuple(env.companies.ids) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
            yield env
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the Odoo registry boundary
        raise OrmToolError("service_unavailable", 503) from None


def _runtime_query_replay_guard(claims: QueryDelegationPayload, scope: str) -> None:
    try:
        with _runtime_query_environment(claims) as env:
            consumed = env["odoo.ai.delegation.use"]._consume(
                jti=claims.jti,
                scope=scope,
                expires_at=claims.expires_at,
            )
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the technical ledger boundary
        raise OrmToolError("service_unavailable", 503) from None
    if consumed is not True:
        raise OrmToolError("delegation_replayed", 403)


def _utc_now() -> datetime:
    return datetime.now(UTC)
