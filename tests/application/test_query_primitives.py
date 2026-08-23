import asyncio
from datetime import UTC, datetime

import pytest

from odoo_ai.application import QueryPrimitiveError, QueryPrimitiveService
from odoo_ai.contracts import (
    AggregateGroup,
    AggregateRecordsRequest,
    AggregateRecordsResult,
    AggregateValue,
    EffectiveFieldSchema,
    EffectiveModelSchema,
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    QueryAggregateOperation,
    QueryCondition,
    QueryFilter,
    QueryMetric,
    QueryOperator,
    QueryRecord,
    QueryRecordsRequest,
    QueryRecordsResult,
    QuerySort,
    QuerySortDirection,
    export_public_json_schemas,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
SCHEMA_ID = "sha256:" + "a" * 64


def _field(
    name: str,
    field_type: str,
    *,
    searchable: bool = True,
    sortable: bool = True,
    groupable: bool = True,
) -> EffectiveFieldSchema:
    return EffectiveFieldSchema(
        name=name,
        label=name,
        field_type=field_type,
        relation="res.partner" if field_type == "many2one" else None,
        required=False,
        readonly=False,
        searchable=searchable,
        sortable=sortable,
        groupable=groupable,
        selection=None,
    )


def _schema() -> EffectiveModelSchema:
    return EffectiveModelSchema(
        schema_id=SCHEMA_ID,
        model="sale.order",
        label="Sales Order",
        revision=SCHEMA_ID,
        fields={
            "amount_total": _field("amount_total", "monetary", groupable=False),
            "id": _field("id", "integer"),
            "name": _field("name", "char"),
            "partner_id": _field("partner_id", "many2one"),
        },
        captured_for_user=17,
        policy_revision="m5-query-read-v1",
        captured_at=NOW,
    )


class FakeQueryGateway:
    def __init__(self) -> None:
        self.query_calls: list[QueryRecordsRequest] = []
        self.aggregate_calls: list[AggregateRecordsRequest] = []

    async def get_query_model_metadata(self, model: str) -> Evidence:
        raise AssertionError("schema metadata is not needed in these execution tests")

    async def query_records(self, request: QueryRecordsRequest) -> QueryRecordsResult:
        self.query_calls.append(request)
        rows = ()
        if request.filter.conditions[0].value != "missing":
            rows = (
                QueryRecord(
                    id=4,
                    fields={
                        name: {"name": "SO004", "amount_total": 42.5}[name]
                        for name in request.fields
                    },
                ),
            )
        return QueryRecordsResult(
            model=request.model,
            schema_id=request.schema_id,
            query=request,
            records=rows,
            returned_count=len(rows),
            limit=request.limit,
            truncated=False,
            captured_at=NOW,
        )

    async def aggregate_records(
        self, request: AggregateRecordsRequest
    ) -> AggregateRecordsResult:
        self.aggregate_calls.append(request)
        return AggregateRecordsResult(
            model=request.model,
            schema_id=request.schema_id,
            query=request,
            groups=(
                AggregateGroup(
                    group={name: 9 for name in request.group_by},
                    metrics=tuple(
                        AggregateValue(
                            operation=metric.operation,
                            field=metric.field,
                            value=(
                                2
                                if metric.operation is QueryAggregateOperation.COUNT
                                else 84.0
                            ),
                        )
                        for metric in request.metrics
                    ),
                ),
            ),
            returned_group_count=1,
            group_limit=request.group_limit,
            truncated=False,
            captured_at=NOW,
        )


def _record_request(
    *, value: str = "SO", operator: QueryOperator = QueryOperator.CONTAINS
):
    return QueryRecordsRequest(
        model="sale.order",
        schema_id=SCHEMA_ID,
        fields=("name", "amount_total"),
        filter=QueryFilter(
            conditions=(QueryCondition(field="name", operator=operator, value=value),)
        ),
        order=(QuerySort(field="amount_total", direction=QuerySortDirection.DESC),),
        limit=10,
    )


def test_valid_filter_sort_and_sql_like_value_remain_structured_data() -> None:
    gateway = FakeQueryGateway()
    request = _record_request(value="x' OR 1=1 --")

    execution = asyncio.run(
        QueryPrimitiveService(gateway).query_records(request, schema=_schema())
    )

    assert gateway.query_calls == [request]
    assert execution.result.returned_count == 1
    assert execution.evidence.kind is EvidenceKind.RECORD
    assert execution.evidence.status is EvidenceStatus.CHECKED
    assert execution.evidence.pointer == {
        "model": "sale.order",
        "operation": "query_records",
        "provider": "odoo_query",
        "schema_id": SCHEMA_ID,
    }
    assert "x' OR 1=1 --" in execution.evidence.model_dump_json()


def test_empty_result_is_checked_and_citable() -> None:
    execution = asyncio.run(
        QueryPrimitiveService(FakeQueryGateway()).query_records(
            _record_request(value="missing"), schema=_schema()
        )
    )

    assert execution.result.records == ()
    assert execution.evidence.status is EvidenceStatus.CHECKED
    assert "no matching data" in execution.evidence.summary


def test_field_operator_and_schema_tampering_fail_before_gateway() -> None:
    gateway = FakeQueryGateway()
    service = QueryPrimitiveService(gateway)

    with pytest.raises(QueryPrimitiveError, match="operator_not_allowed"):
        asyncio.run(
            service.query_records(
                _record_request(value="2", operator=QueryOperator.GT), schema=_schema()
            )
        )
    with pytest.raises(QueryPrimitiveError, match="field_not_in_schema"):
        asyncio.run(
            service.query_records(
                _record_request().model_copy(update={"fields": ("secret",)}),
                schema=_schema(),
            )
        )
    with pytest.raises(QueryPrimitiveError, match="schema_binding_invalid"):
        asyncio.run(
            service.query_records(
                _record_request().model_copy(
                    update={"schema_id": "sha256:" + "b" * 64}
                ),
                schema=_schema(),
            )
        )

    assert gateway.query_calls == []


def test_count_sum_and_group_by_are_validated_and_evidenced() -> None:
    gateway = FakeQueryGateway()
    request = AggregateRecordsRequest(
        model="sale.order",
        schema_id=SCHEMA_ID,
        metrics=(
            QueryMetric(operation=QueryAggregateOperation.COUNT),
            QueryMetric(operation=QueryAggregateOperation.SUM, field="amount_total"),
        ),
        group_by=("partner_id",),
        group_limit=10,
    )

    execution = asyncio.run(
        QueryPrimitiveService(gateway).aggregate_records(request, schema=_schema())
    )

    assert gateway.aggregate_calls == [request]
    assert execution.result.groups[0].metrics[0].value == 2
    assert execution.evidence.status is EvidenceStatus.CHECKED
    assert execution.evidence.pointer["operation"] == "aggregate_records"


def test_aggregate_type_policy_rejects_sum_on_text() -> None:
    request = AggregateRecordsRequest(
        model="sale.order",
        schema_id=SCHEMA_ID,
        metrics=(QueryMetric(operation=QueryAggregateOperation.SUM, field="name"),),
    )

    with pytest.raises(QueryPrimitiveError, match="aggregate_not_allowed"):
        asyncio.run(
            QueryPrimitiveService(FakeQueryGateway()).aggregate_records(
                request, schema=_schema()
            )
        )


def test_query_contract_schemas_are_public_and_reproducible() -> None:
    first = export_public_json_schemas()
    second = export_public_json_schemas()

    for name in (
        "AggregateRecordsRequest",
        "AggregateRecordsResult",
        "QueryCondition",
        "QueryRecordsRequest",
        "QueryRecordsResult",
    ):
        assert first[name] == second[name]
