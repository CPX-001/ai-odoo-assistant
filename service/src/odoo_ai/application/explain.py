"""Evidence-led orchestration for the M4 contextual EXPLAIN workflow."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from odoo_ai.application.context_read import (
    Clock,
    ContextReadError,
    CurrentRecordReader,
    GatewayFactory,
    InstanceLoader,
    TraceEventData,
    TraceWriter,
    validate_context_turn_request,
)
from odoo_ai.contracts import (
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    ExplainCitation,
    ExplainTurnRequest,
    ExplainTurnResponse,
    InstanceProfileSummary,
    RecordCitation,
    SourceCitation,
    ToolExecutionReport,
    ToolSpec,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.ports import ReasoningEngine

MAX_EXPLAIN_TOOL_CALLS = 6
MAX_EXPLAIN_EVIDENCE_ITEMS = 8
MAX_ANSWER_BYTES = 32 * 1024
MAX_ANSWER_CHARS = 16_384

ReportLoader = Callable[[], ToolExecutionReport]


class ExplainTurnError(RuntimeError):
    """Sanitized M4 failure safe for the authenticated Odoo boundary."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ExplainService:
    """Pre-read the record, reason with source tools, and validate all citations."""

    def __init__(
        self,
        *,
        gateway_factory: GatewayFactory,
        reasoning_engine: ReasoningEngine,
        source_tools: Sequence[ToolSpec],
        report_loader: ReportLoader = lambda: ToolExecutionReport(),
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(instance_id="unknown"),
        trace_writer: TraceWriter = lambda trace_id, events: None,
        clock: Clock | None = None,
    ) -> None:
        self._record_reader = CurrentRecordReader(gateway_factory)
        self._reasoning_engine = reasoning_engine
        self._source_tools = tuple(ToolSpec.model_validate(tool) for tool in source_tools)
        self._report_loader = report_loader
        self._instance_loader = instance_loader
        self._trace_writer = trace_writer
        self._clock = clock or _utc_now

    async def run(self, request: ExplainTurnRequest) -> ExplainTurnResponse:
        started = time.monotonic()
        events: list[TraceEventData] = []
        report_taken = False
        self._event(events, "turn.started", "ok", {"turn_id": str(request.turn_id)})
        try:
            now = self._validated_now()
            validate_context_turn_request(request, now=now)
            instance = self._safe_instance_summary()
            self._event(
                events,
                "context.prepared",
                "ok",
                {
                    "instance_state": (
                        "unknown" if instance.instance_id == "unknown" else "detected"
                    ),
                    "model": request.screen.model,
                    "record_count": 1,
                    "workflow": Workflow.EXPLAIN.value,
                },
            )
            current = await self._record_reader.read(
                request,
                event=lambda name, status, attributes: self._event(
                    events, name, status, attributes
                ),
            )
            self._event(
                events,
                "evidence.added",
                "ok",
                {
                    "evidence_count": 1,
                    "evidence_kind": "record",
                    "evidence_origin": "live",
                },
            )
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                workflow_hint=Workflow.EXPLAIN,
                instance=instance,
                live_evidence=[current.evidence],
                conversation_state=ConversationState(
                    current_screen=request.screen,
                    mentioned_records=[current.snapshot.record],
                ),
                limits=TurnLimits(
                    max_tool_calls=MAX_EXPLAIN_TOOL_CALLS,
                    max_evidence_items=MAX_EXPLAIN_EVIDENCE_ITEMS,
                ),
            )
            self._event(
                events,
                "reasoning.started",
                "ok",
                {"tool_count": len(self._source_tools), "workflow": "EXPLAIN"},
            )
            answer = await self._reasoning_engine.run_turn(
                context,
                list(self._source_tools),
                AnswerEnvelope.model_json_schema(),
            )
            report = self._report_loader()
            report_taken = True
            self._append_tool_report(events, report)
            self._event(events, "reasoning.completed", "ok", {"workflow": "EXPLAIN"})
            validated_answer, citations = _validated_answer(
                answer,
                current_record=current.evidence,
                retrieved=report.retrieved_evidence,
                screen_model=cast(str, request.screen.model),
                screen_res_id=cast(int, request.screen.res_id),
            )
            self._event(
                events,
                "answer.validated",
                "ok",
                {
                    "citation_count": len(citations),
                    "confidence": validated_answer.confidence.value,
                    "workflow": validated_answer.workflow.value,
                },
            )
            response = ExplainTurnResponse(
                turn_id=request.turn_id,
                answer_markdown=validated_answer.answer_markdown,
                confidence=validated_answer.confidence,
                limitations=tuple(validated_answer.limitations),
                citations=citations,
                completed_at=self._validated_now(),
            )
            _reject_secret_in_response(
                response,
                request.delegation_token.get_secret_value(),
            )
            self._event(
                events,
                "turn.completed",
                "ok",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "workflow": "EXPLAIN",
                },
            )
            return response
        except ExplainTurnError as error:
            self._error_event(events, error.code, started)
            raise
        except ContextReadError as error:
            self._error_event(events, error.code, started)
            raise ExplainTurnError(error.code, error.status_code) from None
        except Exception as error:
            code, status_code = _explain_failure(error)
            self._error_event(events, code, started)
            raise ExplainTurnError(code, status_code) from None
        finally:
            if not report_taken:
                try:
                    terminal: list[TraceEventData] = []
                    while events and events[-1].event_name in {
                        "reasoning.completed",
                        "turn.completed",
                    }:
                        terminal.insert(0, events.pop())
                    try:
                        self._append_tool_report(events, self._report_loader())
                    finally:
                        events.extend(terminal)
                except Exception:
                    pass
            try:
                self._trace_writer(request.turn_id, tuple(events))
            except Exception:
                pass

    def _validated_now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ExplainTurnError("clock_unavailable", 503)
        return now.astimezone(UTC)

    def _safe_instance_summary(self) -> InstanceProfileSummary:
        try:
            result = self._instance_loader()
        except Exception:
            return InstanceProfileSummary(instance_id="unknown")
        return (
            result
            if isinstance(result, InstanceProfileSummary)
            else InstanceProfileSummary(instance_id="unknown")
        )

    @staticmethod
    def _event(
        events: list[TraceEventData],
        event_name: str,
        status: str,
        attributes: Mapping[str, object],
    ) -> None:
        events.append(TraceEventData(event_name, status, dict(attributes)))

    @classmethod
    def _append_tool_report(
        cls,
        events: list[TraceEventData],
        report: ToolExecutionReport,
    ) -> None:
        for event in report.events:
            cls._event(events, event.event_name, event.status, event.attributes)
        for evidence in report.retrieved_evidence:
            cls._event(
                events,
                "evidence.added",
                "ok",
                {
                    "evidence_kind": evidence.kind.value,
                    "evidence_status": evidence.status.value,
                },
            )

    @classmethod
    def _error_event(
        cls,
        events: list[TraceEventData],
        code: str,
        started: float,
    ) -> None:
        names = {event.event_name for event in events}
        if "reasoning.started" in names and "reasoning.completed" not in names:
            cls._event(
                events,
                "reasoning.completed",
                "error",
                {"error_code": code, "workflow": "EXPLAIN"},
            )
        cls._event(
            events,
            "turn.completed",
            "error",
            {
                "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                "error_code": code,
                "workflow": "EXPLAIN",
            },
        )


def _validated_answer(
    answer: AnswerEnvelope,
    *,
    current_record: Evidence,
    retrieved: Sequence[Evidence],
    screen_model: str,
    screen_res_id: int,
) -> tuple[AnswerEnvelope, tuple[ExplainCitation, ...]]:
    if answer.workflow is not Workflow.EXPLAIN:
        raise ExplainTurnError("answer_workflow_invalid", 502)
    if answer.proposed_action is not None:
        raise ExplainTurnError("answer_action_not_allowed", 502)
    if (
        not answer.answer_markdown
        or len(answer.answer_markdown) > MAX_ANSWER_CHARS
        or len(answer.answer_markdown.encode("utf-8")) > MAX_ANSWER_BYTES
    ):
        raise ExplainTurnError("answer_invalid", 502)

    limitations = tuple(dict.fromkeys(answer.limitations))
    if len(limitations) > 8 or any(not value or len(value) > 1_024 for value in limitations):
        raise ExplainTurnError("answer_invalid", 502)
    references = tuple(dict.fromkeys(answer.evidence_refs))
    all_evidence = (current_record, *retrieved)
    by_id: dict[UUID, Evidence] = {}
    canonical: dict[UUID, str] = {}
    for evidence in all_evidence:
        value = evidence.model_dump_json()
        if evidence.evidence_id in canonical and canonical[evidence.evidence_id] != value:
            raise ExplainTurnError("evidence_duplicate_conflict", 502)
        canonical[evidence.evidence_id] = value
        by_id[evidence.evidence_id] = evidence
    try:
        cited = tuple(by_id[reference] for reference in references)
    except KeyError:
        raise ExplainTurnError("evidence_ref_unknown", 502) from None
    if any(evidence.status is not EvidenceStatus.CHECKED for evidence in cited):
        raise ExplainTurnError("evidence_not_checked", 502)

    citations = tuple(
        _citation(
            evidence,
            screen_model=screen_model,
            screen_res_id=screen_res_id,
        )
        for evidence in cited
    )
    confidence = answer.confidence
    cited_kinds = {evidence.kind for evidence in cited}
    if confidence is AnswerConfidence.HIGH and not {
        EvidenceKind.RECORD,
        EvidenceKind.SOURCE,
    }.issubset(cited_kinds):
        confidence = AnswerConfidence.MEDIUM
        limitation = (
            "La confianza se ha reducido porque faltan citas comprobadas del "
            "registro actual y del source."
        )
        limitations = (*limitations[:7], limitation)
    return (
        answer.model_copy(
            update={
                "confidence": confidence,
                "evidence_refs": list(references),
                "limitations": list(limitations),
            }
        ),
        citations,
    )


def _citation(
    evidence: Evidence,
    *,
    screen_model: str,
    screen_res_id: int,
) -> ExplainCitation:
    if evidence.kind is EvidenceKind.RECORD:
        pointer = evidence.pointer
        payload_record = evidence.payload.get("record")
        if (
            not isinstance(pointer, dict)
            or set(pointer) != {"model", "res_id"}
            or pointer.get("model") != screen_model
            or pointer.get("res_id") != screen_res_id
            or not isinstance(payload_record, dict)
            or payload_record.get("model") != screen_model
            or payload_record.get("id") != screen_res_id
            or evidence.observed_at is None
        ):
            raise ExplainTurnError("record_citation_invalid", 502)
        display_name = payload_record.get("display_name")
        if display_name is not None and (
            not isinstance(display_name, str) or len(display_name) > 512
        ):
            raise ExplainTurnError("record_citation_invalid", 502)
        return RecordCitation(
            evidence_id=evidence.evidence_id,
            model=screen_model,
            id=screen_res_id,
            display_name=display_name,
            captured_at=evidence.observed_at,
        )
    if evidence.kind is EvidenceKind.SOURCE:
        pointer = evidence.pointer
        module = evidence.payload.get("module")
        provenance = evidence.payload.get("provenance", "unknown")
        logical_path = pointer.get("logical_path") if isinstance(pointer, dict) else None
        start_line = pointer.get("start_line") if isinstance(pointer, dict) else None
        end_line = pointer.get("end_line") if isinstance(pointer, dict) else None
        if (
            not isinstance(pointer, dict)
            or not isinstance(module, str)
            or not isinstance(provenance, str)
            or not 1 <= len(provenance) <= 64
            or provenance != provenance.strip()
            or any(ord(character) < 32 for character in provenance)
            or re.fullmatch(r"[A-Za-z0-9_]+", module) is None
            or not isinstance(logical_path, str)
            or type(start_line) is not int
            or type(end_line) is not int
            or not isinstance(evidence.fingerprint, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", evidence.fingerprint) is None
        ):
            raise ExplainTurnError("source_citation_invalid", 502)
        assert isinstance(logical_path, str)
        assert type(start_line) is int
        assert type(end_line) is int
        if not _safe_logical_path(logical_path) or start_line <= 0 or end_line < start_line:
            raise ExplainTurnError("source_citation_invalid", 502)
        return SourceCitation(
            evidence_id=evidence.evidence_id,
            module=module,
            logical_path=logical_path,
            start_line=start_line,
            end_line=end_line,
            fingerprint=evidence.fingerprint,
            provenance=provenance,
        )
    raise ExplainTurnError("evidence_kind_not_renderable", 502)


def _safe_logical_path(value: str) -> bool:
    if "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and str(path) == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _reject_secret_in_response(response: ExplainTurnResponse, secret: str) -> None:
    if secret and secret in response.model_dump_json():
        raise ExplainTurnError("unsafe_response", 502)


def _explain_failure(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", "engine_unavailable")
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if code in {"invalid_request", "request_too_large"}:
        return code, 413 if code == "request_too_large" else 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    if "timeout" in code or "deadline" in code:
        return "engine_timeout", 504
    if code.startswith("source_") or code in {
        "stale_source",
        "evidence_not_checked",
    }:
        return "evidence_unavailable", 503
    if code.startswith("codex_"):
        return "engine_unavailable", 503
    return "engine_unavailable", 503


def _utc_now() -> datetime:
    return datetime.now(UTC)
