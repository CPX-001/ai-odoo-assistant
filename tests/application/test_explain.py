import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from odoo_ai.adapters import OdooGatewayError, source_tool_specs
from odoo_ai.application import ExplainService, ExplainTurnError, TraceEventData
from odoo_ai.contracts import (
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    ExplainTurnRequest,
    ProposedAction,
    RecordRef,
    RecordSnapshot,
    ToolExecutionEvent,
    ToolExecutionReport,
    Workflow,
)

TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
SOURCE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
DELEGATION_TOKEN = "v1." + "d" * 96
SOURCE_TEXT = "def action_confirm(self):\n    self.env['project.task'].create({})"


class FakeGateway:
    def __init__(self, failure: str | None = None) -> None:
        self.failure = failure
        self.read_completed = False

    async def get_model_metadata(self, model: str) -> Evidence:
        if self.failure:
            raise OdooGatewayError(self.failure)
        return Evidence(
            evidence_id="11111111-1111-4111-8111-111111111111",
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Metadata",
            summary="Effective metadata",
            payload={
                "model": model,
                "fields": {
                    "display_name": {"type": "char"},
                    "name": {"type": "char"},
                    "state": {"type": "selection"},
                    "company_id": {"type": "many2one"},
                },
            },
            sensitivity=EvidenceSensitivity.TECHNICAL,
        )

    async def read_records(
        self, records: list[RecordRef], fields: list[str]
    ) -> list[RecordSnapshot]:
        self.read_completed = True
        values: dict[str, Any] = {
            "display_name": "S00042",
            "name": "S00042",
            "state": "sale",
            "company_id": [3, "My Company"],
        }
        return [
            RecordSnapshot(
                record=RecordRef(
                    model=records[0].model,
                    id=records[0].id,
                    display_name="S00042",
                ),
                fields={name: values[name] for name in fields},
                captured_at=datetime.now(UTC),
                provenance={"provider": "fake"},
            )
        ]


class FakeGatewayFactory:
    def __init__(self, gateway: FakeGateway) -> None:
        self.gateway = gateway

    def for_turn(self, *, turn_id: UUID, delegation_token: object) -> FakeGateway:
        assert turn_id == TURN_ID
        assert delegation_token.get_secret_value() == DELEGATION_TOKEN
        return self.gateway


class ReportHolder:
    def __init__(self, report: ToolExecutionReport | None = None) -> None:
        self.report = report or ToolExecutionReport()

    def take(self) -> ToolExecutionReport:
        report = self.report
        self.report = ToolExecutionReport()
        return report


class FakeEngine:
    def __init__(
        self,
        gateway: FakeGateway,
        answer_factory,
    ) -> None:
        self.gateway = gateway
        self.answer_factory = answer_factory
        self.context: ContextPack | None = None

    async def run_turn(self, context, tools, output_schema):
        assert self.gateway.read_completed is True
        assert [tool.name for tool in tools] == [
            "source.find_symbol",
            "source.find_model_extensions",
            "source.read_excerpt",
        ]
        assert output_schema == AnswerEnvelope.model_json_schema()
        self.context = context
        return self.answer_factory(context)


def _request() -> ExplainTurnRequest:
    return ExplainTurnRequest.model_validate(
        {
            "turn_id": str(TURN_ID),
            "message": "¿Por qué confirmar este pedido crea una tarea?",
            "screen": {
                "action_id": 42,
                "menu_id": 7,
                "view_type": "form",
                "model": "sale.order",
                "res_id": 42,
                "selected_ids": [42],
                "allowed_context_subset": {
                    "active_id": 42,
                    "active_model": "sale.order",
                },
                "captured_at": datetime.now(UTC).isoformat(),
            },
            "user": {
                "uid": 17,
                "company_id": 3,
                "allowed_company_ids": [3, 5],
                "lang": "es_ES",
            },
            "delegation_token": DELEGATION_TOKEN,
            "gateway": {"database": "customer-db"},
        }
    )


def _source_evidence(status: EvidenceStatus = EvidenceStatus.CHECKED) -> Evidence:
    return Evidence(
        evidence_id=SOURCE_ID,
        kind=EvidenceKind.SOURCE,
        status=status,
        title="Source: fixture/action_confirm",
        summary="Fingerprint-checked excerpt.",
        payload={
            "module": "odoo_ai_m3_sale_project",
            "provenance": "third_party_or_custom",
            "lines": [{"number": 8, "text": SOURCE_TEXT}],
        },
        pointer={
            "source_file_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "logical_path": "odoo_ai_m3_sale_project/models/sale_order.py",
            "start_line": 8,
            "end_line": 12,
        },
        observed_at=datetime.now(UTC),
        sensitivity=EvidenceSensitivity.TECHNICAL,
        fingerprint="sha256:" + "a" * 64,
    )


def _service(
    answer_factory,
    *,
    gateway: FakeGateway | None = None,
    report: ToolExecutionReport | None = None,
    traces: list[tuple[UUID, tuple[TraceEventData, ...]]] | None = None,
) -> tuple[ExplainService, FakeEngine]:
    effective_gateway = gateway or FakeGateway()
    holder = ReportHolder(report)
    engine = FakeEngine(effective_gateway, answer_factory)
    service = ExplainService(
        gateway_factory=FakeGatewayFactory(effective_gateway),
        reasoning_engine=engine,
        source_tools=source_tool_specs(),
        report_loader=holder.take,
        trace_writer=(
            (lambda trace_id, events: traces.append((trace_id, events)))
            if traces is not None
            else (lambda trace_id, events: None)
        ),
    )
    return service, engine


def test_record_is_reread_before_reasoning_and_supports_medium_answer() -> None:
    def answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="El pedido está confirmado.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.MEDIUM,
            evidence_refs=[context.live_evidence[0].evidence_id],
        )

    service, engine = _service(answer)
    response = asyncio.run(service.run(_request()))

    assert response.confidence is AnswerConfidence.MEDIUM
    assert response.citations[0].kind == "record"
    assert response.citations[0].model == "sale.order"
    assert engine.context is not None
    assert engine.context.workflow_hint is Workflow.EXPLAIN
    assert engine.context.limits.max_tool_calls == 6
    assert engine.context.limits.max_evidence_items == 8
    assert engine.context.conversation_state.short_summary == ""


def test_checked_record_and_source_refs_render_high_confidence_citations() -> None:
    source = _source_evidence()

    def answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="El override crea la tarea bajo la condición mostrada.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.HIGH,
            evidence_refs=[context.live_evidence[0].evidence_id, SOURCE_ID, SOURCE_ID],
        )

    report = ToolExecutionReport(
        events=(
            ToolExecutionEvent("tool.requested", "ok", {"tool_name": "source.read_excerpt"}),
            ToolExecutionEvent(
                "tool.completed",
                "ok",
                {"tool_name": "source.read_excerpt", "evidence_count": 1},
            ),
        ),
        retrieved_evidence=(source,),
    )
    service, _ = _service(answer, report=report)

    response = asyncio.run(service.run(_request()))

    assert response.confidence is AnswerConfidence.HIGH
    assert [citation.kind for citation in response.citations] == ["record", "source"]
    assert response.citations[1].logical_path.endswith("models/sale_order.py")
    assert response.citations[1].fingerprint == source.fingerprint


def test_invented_ref_and_proposed_action_are_rejected() -> None:
    invented = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

    def invented_answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="Invented.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.LOW,
            evidence_refs=[invented],
        )

    service, _ = _service(invented_answer)
    with pytest.raises(ExplainTurnError, match="evidence_ref_unknown"):
        asyncio.run(service.run(_request()))

    def action_answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="Action.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.LOW,
            evidence_refs=[context.live_evidence[0].evidence_id],
            proposed_action=ProposedAction(action_type="write", summary="No"),
        )

    service, _ = _service(action_answer)
    with pytest.raises(ExplainTurnError, match="answer_action_not_allowed"):
        asyncio.run(service.run(_request()))


def test_high_confidence_is_degraded_when_source_is_unavailable() -> None:
    def answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="Sólo consta el registro.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.HIGH,
            evidence_refs=[context.live_evidence[0].evidence_id],
        )

    service, _ = _service(answer)
    response = asyncio.run(service.run(_request()))

    assert response.confidence is AnswerConfidence.MEDIUM
    assert "source" in response.limitations[0]


def test_access_denied_remains_access_denied() -> None:
    service, _ = _service(
        lambda context: None,
        gateway=FakeGateway(failure="access_denied"),
    )

    with pytest.raises(ExplainTurnError) as failure:
        asyncio.run(service.run(_request()))

    assert failure.value.code == "access_denied"
    assert failure.value.status_code == 403


def test_trace_contains_metadata_but_not_token_prompt_or_raw_source() -> None:
    traces: list[tuple[UUID, tuple[TraceEventData, ...]]] = []

    def answer(context: ContextPack) -> AnswerEnvelope:
        return AnswerEnvelope(
            answer_markdown="Causa comprobada.",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.HIGH,
            evidence_refs=[context.live_evidence[0].evidence_id, SOURCE_ID],
        )

    service, _ = _service(
        answer,
        report=ToolExecutionReport(
            events=(
                ToolExecutionEvent(
                    "tool.requested",
                    "ok",
                    {"tool_name": "source.read_excerpt"},
                ),
                ToolExecutionEvent(
                    "tool.completed",
                    "ok",
                    {"evidence_count": 1, "tool_name": "source.read_excerpt"},
                ),
            ),
            retrieved_evidence=(_source_evidence(),),
        ),
        traces=traces,
    )
    asyncio.run(service.run(_request()))

    serialized = repr(traces)
    assert DELEGATION_TOKEN not in serialized
    assert "¿Por qué confirmar" not in serialized
    assert SOURCE_TEXT not in serialized
    assert "reasoning.started" in serialized
    assert "answer.validated" in serialized
    assert "evidence.added" in serialized
    events = traces[0][1]
    names = [event.event_name for event in events]
    source_requested = next(
        index
        for index, event in enumerate(events)
        if event.event_name == "tool.requested"
        and event.attributes.get("tool_name") == "source.read_excerpt"
    )
    source_completed = next(
        index
        for index, event in enumerate(events)
        if event.event_name == "tool.completed"
        and event.attributes.get("tool_name") == "source.read_excerpt"
    )
    assert names.index("reasoning.started") < source_requested
    assert source_completed < names.index("reasoning.completed")
