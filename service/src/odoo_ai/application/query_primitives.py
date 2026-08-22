"""Schema-validated QUERY primitives and checked evidence construction."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, cast
from uuid import uuid4

from odoo_ai.application.effective_schema import (
    EffectiveSchemaPolicy,
    EffectiveSchemaResult,
    EffectiveSchemaService,
)
from odoo_ai.contracts import (
    AggregateRecordsRequest,
    AggregateRecordsResult,
    EffectiveFieldSchema,
    EffectiveModelSchema,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    QueryAggregateOperation,
    QueryOperator,
    QueryRecordsRequest,
    QueryRecordsResult,
)
from odoo_ai.ports import ModelMetadataGateway, OdooQueryGateway

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

MAX_QUERY_VALUE_STRING: Final = 1_024
MAX_QUERY_LIST_VALUES: Final = 32

_OPERATORS_BY_TYPE: Final = {
    "boolean": frozenset(
        {QueryOperator.EQ, QueryOperator.NE, QueryOperator.IN, QueryOperator.NOT_IN}
    ),
    "char": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
            QueryOperator.CONTAINS,
        }
    ),
    "date": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.LT,
            QueryOperator.LTE,
            QueryOperator.GT,
            QueryOperator.GTE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
        }
    ),
    "datetime": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.LT,
            QueryOperator.LTE,
            QueryOperator.GT,
            QueryOperator.GTE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
        }
    ),
    "float": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.LT,
            QueryOperator.LTE,
            QueryOperator.GT,
            QueryOperator.GTE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
        }
    ),
    "html": frozenset({QueryOperator.EQ, QueryOperator.NE, QueryOperator.CONTAINS}),
    "integer": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.LT,
            QueryOperator.LTE,
            QueryOperator.GT,
            QueryOperator.GTE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
        }
    ),
    "many2one": frozenset(
        {QueryOperator.EQ, QueryOperator.NE, QueryOperator.IN, QueryOperator.NOT_IN}
    ),
    "monetary": frozenset(
        {
            QueryOperator.EQ,
            QueryOperator.NE,
            QueryOperator.LT,
            QueryOperator.LTE,
            QueryOperator.GT,
            QueryOperator.GTE,
            QueryOperator.IN,
            QueryOperator.NOT_IN,
        }
    ),
    "selection": frozenset(
        {QueryOperator.EQ, QueryOperator.NE, QueryOperator.IN, QueryOperator.NOT_IN}
    ),
    "text": frozenset({QueryOperator.EQ, QueryOperator.NE, QueryOperator.CONTAINS}),
}
_SUM_TYPES = frozenset({"float", "integer", "monetary"})
_MIN_MAX_TYPES = frozenset({"date", "datetime", "float", "integer", "monetary"})


class QueryPrimitiveError(RuntimeError):
    """Sanitized QUERY validation or execution failure."""

    def __init__(self, code: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class QueryRecordsExecution:
    result: QueryRecordsResult
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class AggregateRecordsExecution:
    result: AggregateRecordsResult
    evidence: Evidence


class _QueryMetadataGateway(ModelMetadataGateway):
    def __init__(self, gateway: OdooQueryGateway) -> None:
        self._gateway = gateway

    async def get_model_metadata(self, model: str) -> Evidence:
        return await self._gateway.get_query_model_metadata(model)


class QueryPrimitiveService:
    """Validate every model/field/operator against the turn's effective schema."""

    def __init__(
        self,
        gateway: OdooQueryGateway,
        *,
        schema_policy: EffectiveSchemaPolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._schemas = EffectiveSchemaService(_QueryMetadataGateway(gateway), policy=schema_policy)

    async def get_effective_schema(
        self, *, model: str, captured_for_user: int
    ) -> EffectiveSchemaResult:
        return await self._schemas.get(
            model=model,
            captured_for_user=captured_for_user,
        )

    async def query_records(
        self,
        request: QueryRecordsRequest,
        *,
        schema: EffectiveModelSchema,
    ) -> QueryRecordsExecution:
        _validate_schema_binding(request.model, request.schema_id, schema)
        _validate_record_query(request, schema)
        try:
            result = await self._gateway.query_records(request)
        except QueryPrimitiveError:
            raise
        except Exception:
            raise QueryPrimitiveError("query_unavailable", 502) from None
        return QueryRecordsExecution(
            result=result,
            evidence=_query_evidence(
                operation="query_records",
                model=request.model,
                schema_id=request.schema_id,
                result=result,
                captured_at=result.captured_at,
                empty=result.returned_count == 0,
            ),
        )

    async def aggregate_records(
        self,
        request: AggregateRecordsRequest,
        *,
        schema: EffectiveModelSchema,
    ) -> AggregateRecordsExecution:
        _validate_schema_binding(request.model, request.schema_id, schema)
        _validate_aggregate_query(request, schema)
        try:
            result = await self._gateway.aggregate_records(request)
        except QueryPrimitiveError:
            raise
        except Exception:
            raise QueryPrimitiveError("query_unavailable", 502) from None
        return AggregateRecordsExecution(
            result=result,
            evidence=_query_evidence(
                operation="aggregate_records",
                model=request.model,
                schema_id=request.schema_id,
                result=result,
                captured_at=result.captured_at,
                empty=_aggregate_is_empty(result),
            ),
        )


def _validate_schema_binding(model: str, schema_id: str, schema: EffectiveModelSchema) -> None:
    if model != schema.model or schema_id != schema.schema_id:
        raise QueryPrimitiveError("schema_binding_invalid")


def _validate_record_query(request: QueryRecordsRequest, schema: EffectiveModelSchema) -> None:
    for name in request.fields:
        _field(schema, name)
    for condition in request.filter.conditions:
        field = _field(schema, condition.field)
        if not field.searchable or condition.operator not in _OPERATORS_BY_TYPE.get(
            field.field_type, frozenset()
        ):
            raise QueryPrimitiveError("operator_not_allowed")
        _validate_condition_value(
            condition.value,
            field=field,
            operator=condition.operator,
        )
    for sort in request.order:
        if not _field(schema, sort.field).sortable:
            raise QueryPrimitiveError("field_not_sortable")


def _validate_aggregate_query(
    request: AggregateRecordsRequest, schema: EffectiveModelSchema
) -> None:
    for condition in request.filter.conditions:
        field = _field(schema, condition.field)
        if not field.searchable or condition.operator not in _OPERATORS_BY_TYPE.get(
            field.field_type, frozenset()
        ):
            raise QueryPrimitiveError("operator_not_allowed")
        _validate_condition_value(
            condition.value,
            field=field,
            operator=condition.operator,
        )
    for name in request.group_by:
        if not _field(schema, name).groupable:
            raise QueryPrimitiveError("field_not_groupable")
    for metric in request.metrics:
        if metric.operation is QueryAggregateOperation.COUNT:
            continue
        assert metric.field is not None
        field = _field(schema, metric.field)
        allowed = _SUM_TYPES if metric.operation is QueryAggregateOperation.SUM else _MIN_MAX_TYPES
        if field.field_type not in allowed:
            raise QueryPrimitiveError("aggregate_not_allowed")


def _field(schema: EffectiveModelSchema, name: str) -> EffectiveFieldSchema:
    try:
        return schema.fields[name]
    except KeyError:
        raise QueryPrimitiveError("field_not_in_schema") from None


def _validate_condition_value(
    value: object,
    *,
    field: EffectiveFieldSchema,
    operator: QueryOperator,
) -> None:
    if operator in {QueryOperator.IN, QueryOperator.NOT_IN}:
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_QUERY_LIST_VALUES:
            raise QueryPrimitiveError("query_value_invalid")
        for item in value:
            _validate_scalar(item, field=field, allow_none=False)
        return
    if operator is QueryOperator.CONTAINS:
        if not isinstance(value, str) or not 1 <= len(value) <= MAX_QUERY_VALUE_STRING:
            raise QueryPrimitiveError("query_value_invalid")
        return
    _validate_scalar(
        value,
        field=field,
        allow_none=operator in {QueryOperator.EQ, QueryOperator.NE},
    )


def _validate_scalar(
    value: object,
    *,
    field: EffectiveFieldSchema,
    allow_none: bool,
) -> None:
    if value is None:
        if not allow_none:
            raise QueryPrimitiveError("query_value_invalid")
        return
    field_type = field.field_type
    if field_type == "boolean":
        valid = isinstance(value, bool)
    elif field_type in {"integer", "many2one"}:
        valid = type(value) is int and (field_type != "many2one" or value > 0)
    elif field_type in {"float", "monetary"}:
        valid = (
            not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        )
    elif field_type in {"char", "html", "selection", "text"}:
        valid = isinstance(value, str) and len(value) <= MAX_QUERY_VALUE_STRING
        if valid and field_type == "selection" and field.selection is not None:
            valid = value in {option.value for option in field.selection}
    elif field_type == "date":
        valid = _valid_date(value)
    elif field_type == "datetime":
        valid = _valid_datetime(value)
    else:
        valid = False
    if not valid:
        raise QueryPrimitiveError("query_value_invalid")


def _valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_datetime(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 64:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _query_evidence(
    *,
    operation: str,
    model: str,
    schema_id: str,
    result: QueryRecordsResult | AggregateRecordsResult,
    captured_at: datetime,
    empty: bool,
) -> Evidence:
    payload = cast(dict[str, JsonValue], result.model_dump(mode="json"))
    canonical = {
        "model": model,
        "operation": operation,
        "result": payload,
        "schema_id": schema_id,
    }
    fingerprint = f"sha256:{hashlib.sha256(_canonical_bytes(canonical)).hexdigest()}"
    return Evidence(
        evidence_id=uuid4(),
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title=f"Odoo QUERY: {model}",
        summary=(
            "The bounded ORM query returned no matching data."
            if empty
            else "The bounded ORM query returned checked data under the effective user."
        ),
        payload=payload,
        pointer={
            "model": model,
            "operation": operation,
            "provider": "odoo_query",
            "schema_id": schema_id,
        },
        observed_at=captured_at,
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint=fingerprint,
    )


def _aggregate_is_empty(result: AggregateRecordsResult) -> bool:
    if not result.groups:
        return True
    if result.query.group_by:
        return False
    count_values = [
        metric.value
        for metric in result.groups[0].metrics
        if metric.operation is QueryAggregateOperation.COUNT
    ]
    return bool(count_values) and count_values == [0]


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise QueryPrimitiveError("query_result_invalid", 502) from None
