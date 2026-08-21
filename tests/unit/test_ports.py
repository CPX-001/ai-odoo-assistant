import asyncio
from datetime import UTC, datetime
from uuid import UUID

from odoo_ai.contracts import (
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    LogCorrelation,
    LogEvidence,
    LogSearchRequest,
    RecordRef,
    RecordSnapshot,
    ScreenContext,
    TimestampRange,
    ToolSpec,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)
from odoo_ai.ports import LogProvider, OdooGateway, ReasoningEngine


def _evidence(kind: EvidenceKind = EvidenceKind.METADATA) -> Evidence:
    return Evidence(
        evidence_id=UUID("12345678-1234-5678-1234-567812345678"),
        kind=kind,
        status=EvidenceStatus.CHECKED,
        title="Odoo metadata",
        summary="Metadata read under the effective user.",
        sensitivity=EvidenceSensitivity.TECHNICAL,
    )


class FakeReasoningEngine:
    async def run_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        output_schema: dict[str, object],
    ) -> AnswerEnvelope:
        del context, tools, output_schema
        return AnswerEnvelope(
            answer_markdown="Fake answer",
            workflow=Workflow.EXPLAIN,
            confidence=AnswerConfidence.HIGH,
            evidence_refs=[_evidence().evidence_id],
        )


class FakeOdooGateway:
    async def read_records(
        self,
        records: list[RecordRef],
        fields: list[str],
    ) -> list[RecordSnapshot]:
        return [
            RecordSnapshot(
                record=record,
                fields={field: f"value:{field}" for field in fields},
                captured_at=datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
                provenance={"gateway": "fake"},
            )
            for record in records
        ]

    async def get_model_metadata(self, model: str) -> Evidence:
        return _evidence().model_copy(update={"payload": {"model": model}})


class FakeLogProvider:
    async def search(self, request: LogSearchRequest) -> list[LogEvidence]:
        return [
            LogEvidence(
                provider="fake",
                timestamp_range=TimestampRange(from_ts=request.from_ts, to_ts=request.to_ts),
                excerpt="Traceback excerpt",
                traceback_fingerprint="trace-123",
                correlation=LogCorrelation.DIRECT,
            )
        ]

    async def read_traceback(
        self,
        fingerprint: str,
        *,
        max_bytes: int,
    ) -> LogEvidence | None:
        del max_bytes
        results = await self.search(
            LogSearchRequest(terms=[fingerprint], max_lines=20, max_bytes=4096)
        )
        return results[0]


async def _run_engine(engine: ReasoningEngine, context: ContextPack) -> AnswerEnvelope:
    return await engine.run_turn(context, [], AnswerEnvelope.model_json_schema())


async def _read_record(gateway: OdooGateway) -> RecordSnapshot:
    records = await gateway.read_records(
        [RecordRef(model="sale.order", id=56)],
        ["name"],
    )
    return records[0]


async def _search_logs(provider: LogProvider) -> LogEvidence:
    results = await provider.search(
        LogSearchRequest(terms=["action_confirm"], max_lines=50, max_bytes=8192)
    )
    return results[0]


def _context_pack() -> ContextPack:
    screen = ScreenContext(captured_at=datetime(2026, 8, 21, 10, 30, tzinfo=UTC))
    return ContextPack(
        request=UserRequest(message="Explain this record."),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1),
        instance=InstanceProfileSummary(instance_id="odoo-test"),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=3, max_evidence_items=5),
    )


def test_reasoning_engine_fake_is_substitutable() -> None:
    answer = asyncio.run(_run_engine(FakeReasoningEngine(), _context_pack()))

    assert answer.answer_markdown == "Fake answer"


def test_odoo_gateway_fake_is_substitutable_without_generic_execution() -> None:
    snapshot = asyncio.run(_read_record(FakeOdooGateway()))

    assert snapshot.record.id == 56
    assert snapshot.fields == {"name": "value:name"}
    assert not hasattr(OdooGateway, "execute_kw")
    assert not hasattr(OdooGateway, "execute_method")


def test_log_provider_fake_is_substitutable_without_free_form_access() -> None:
    evidence = asyncio.run(_search_logs(FakeLogProvider()))

    assert evidence.traceback_fingerprint == "trace-123"
    assert not hasattr(LogProvider, "run_command")
