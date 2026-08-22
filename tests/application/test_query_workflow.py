import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from odoo_ai.adapters import query_tool_specs
from odoo_ai.application import QueryService, QueryTurnError, TraceEventData
from odoo_ai.contracts import (
    AggregateGroup,
    AggregateRecordsRequest,
    AggregateRecordsResult,
    AggregateValue,
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    ProposedAction,
    QueryAggregateOperation,
    QueryFilter,
    QueryRecord,
    QueryRecordsRequest,
    QueryRecordsResult,
    QueryTurnRequest,
    ToolExecutionEvent,
    ToolExecutionReport,
    Workflow,
)
from odoo_ai.tools import ToolExecutorError

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
TURN_ID = UUID("52345678-1234-5678-1234-567812345678")
QUERY_EVIDENCE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SCHEMA_ID = "sha256:" + "a" * 64
TOKEN = "q1." + "d" * 256


class FakeEngine:
    def __init__(self, answer_factory) -> None:
        self.answer_factory = answer_factory
        self.context: ContextPack | None = None

    async def run_turn(self, context, tools, output_schema):
        self.context = context
        assert [tool.name for tool in tools] == [
            "odoo.get_effective_schema",
            "odoo.query_records",
            "odoo.aggregate_records",
        ]
        assert output_schema == AnswerEnvelope.model_json_schema()
        result = self.answer_factory(context)
        if isinstance(result, Exception):
            raise result
        return result


class ReportHolder:
    def __init__(self, report: ToolExecutionReport) -> None:
        self.report = report

    def take(self) -> ToolExecutionReport:
        result = self.report
        self.report = ToolExecutionReport()
        return result


def _request() -> QueryTurnRequest:
    return QueryTurnRequest.model_validate(
        {
            "turn_id": str(TURN_ID),
            "message": "¿Qué pedidos contienen S?",
            "screen": {
                "view_type": "list",
                "model": "sale.order",
                "selected_ids": [],
                "captured_at": NOW.isoformat(),
            },
            "user": {
                "uid": 17,
                "company_id": 3,
                "allowed_company_ids": [3],
                "lang": "es_ES",
            },
            "delegation_token": TOKEN,
            "gateway": {"database": "customer-db"},
        }
    )


def _record_evidence(*, empty: bool = False, truncated: bool = False) -> Evidence:
    request = QueryRecordsRequest(
        model="sale.order",
        schema_id=SCHEMA_ID,
        fields=("name",),
        filter=QueryFilter(),
        limit=1,
    )
    records = () if empty else (QueryRecord(id=7, fields={"name": "S0007"}),)
    result = QueryRecordsResult(
        model=request.model,
        schema_id=request.schema_id,
        query=request,
        records=records,
        returned_count=len(records),
        limit=request.limit,
        truncated=truncated,
        captured_at=NOW,
    )
    return Evidence(
        evidence_id=QUERY_EVIDENCE_ID,
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="query",
        summary="checked",
        payload=result.model_dump(mode="json"),
        pointer={
            "model": "sale.order",
            "operation": "query_records",
            "provider": "odoo_query",
            "schema_id": SCHEMA_ID,
        },
        observed_at=NOW,
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint="sha256:" + "b" * 64,
    )


def _aggregate_empty_evidence() -> Evidence:
    request = AggregateRecordsRequest(
        model="sale.order",
        schema_id=SCHEMA_ID,
        metrics=(({"operation": "count", "field": None}),),
        group_limit=20,
    )
    result = AggregateRecordsResult(
        model=request.model,
        schema_id=request.schema_id,
        query=request,
        groups=(
            AggregateGroup(
                group={},
                metrics=(
                    AggregateValue(
                        operation=QueryAggregateOperation.COUNT,
                        value=0,
                    ),
                ),
            ),
        ),
        returned_group_count=1,
        group_limit=20,
        truncated=False,
        captured_at=NOW,
    )
    return Evidence(
        evidence_id=QUERY_EVIDENCE_ID,
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="aggregate",
        summary="empty checked",
        payload=result.model_dump(mode="json"),
        pointer={
            "model": "sale.order",
            "operation": "aggregate_records",
            "provider": "odoo_query",
            "schema_id": SCHEMA_ID,
        },
        observed_at=NOW,
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint="sha256:" + "c" * 64,
    )


def _service(answer_factory, evidence: Evidence, traces=None):
    report = ToolExecutionReport(
        events=(
            ToolExecutionEvent(
                "tool.completed",
                "ok",
                {"evidence_count": 1, "tool_name": "odoo.query_records"},
            ),
        ),
        retrieved_evidence=(evidence,),
    )
    holder = ReportHolder(report)
    engine = FakeEngine(answer_factory)
    service = QueryService(
        reasoning_engine=engine,
        query_tools=query_tool_specs(),
        report_loader=holder.take,
        clock=lambda: NOW,
        trace_writer=(
            (lambda trace_id, events: traces.append((trace_id, events)))
            if traces is not None
            else (lambda trace_id, events: None)
        ),
    )
    return service, engine


def _answer(**overrides) -> AnswerEnvelope:
    values = {
        "answer_markdown": "Hay un pedido coincidente.",
        "workflow": Workflow.QUERY,
        "confidence": AnswerConfidence.HIGH,
        "evidence_refs": [QUERY_EVIDENCE_ID],
    }
    values.update(overrides)
    return AnswerEnvelope(**values)


def test_record_query_has_checked_browser_safe_citation() -> None:
    service, engine = _service(lambda context: _answer(), _record_evidence())

    response = asyncio.run(service.run(_request()))

    assert response.workflow is Workflow.QUERY
    assert response.confidence is AnswerConfidence.HIGH
    assert response.citations[0].operation == "query_records"
    assert response.citations[0].returned_count == 1
    assert response.citations[0].empty is False
    assert engine.context is not None
    assert engine.context.workflow_hint is Workflow.QUERY
    assert engine.context.live_evidence == []


def test_checked_empty_aggregate_supports_high_confidence() -> None:
    service, _ = _service(
        lambda context: _answer(answer_markdown="No hay pedidos."),
        _aggregate_empty_evidence(),
    )

    response = asyncio.run(service.run(_request()))

    assert response.confidence is AnswerConfidence.HIGH
    assert response.citations[0].operation == "aggregate_records"
    assert response.citations[0].empty is True


def test_invented_ref_action_and_unacknowledged_truncation_are_rejected() -> None:
    invented = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    service, _ = _service(
        lambda context: _answer(evidence_refs=[invented]),
        _record_evidence(),
    )
    with pytest.raises(QueryTurnError, match="evidence_ref_unknown"):
        asyncio.run(service.run(_request()))

    service, _ = _service(
        lambda context: _answer(
            proposed_action=ProposedAction(action_type="write", summary="No")
        ),
        _record_evidence(),
    )
    with pytest.raises(QueryTurnError, match="answer_action_not_allowed"):
        asyncio.run(service.run(_request()))

    service, _ = _service(lambda context: _answer(), _record_evidence(truncated=True))
    with pytest.raises(QueryTurnError, match="answer_truncation_unacknowledged"):
        asyncio.run(service.run(_request()))


def test_budget_failure_and_traces_are_sanitized() -> None:
    service, _ = _service(
        lambda context: ToolExecutorError("tool_call_budget_exceeded"),
        _record_evidence(),
    )
    with pytest.raises(QueryTurnError) as failure:
        asyncio.run(service.run(_request()))
    assert failure.value.code == "query_budget_exceeded"

    traces: list[tuple[UUID, tuple[TraceEventData, ...]]] = []
    service, _ = _service(lambda context: _answer(), _record_evidence(), traces)
    asyncio.run(service.run(_request()))
    serialized = repr(traces)
    assert TOKEN not in serialized
    assert "¿Qué pedidos" not in serialized
    assert "S0007" not in serialized
    assert "odoo.query_records" in serialized
