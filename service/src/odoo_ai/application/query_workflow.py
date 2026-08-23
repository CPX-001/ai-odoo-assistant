"""Evidence-led orchestration for the read-only QUERY workflow."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from odoo_ai.application.context_read import (
    Clock,
    ContextReadError,
    InstanceLoader,
    TraceEventData,
    TraceWriter,
    validate_query_turn_request,
)
from odoo_ai.contracts import (
    AggregateRecordsResult,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    InstanceProfileSummary,
    QueryCitation,
    QueryRecordsResult,
    QueryTurnRequest,
    QueryTurnResponse,
    ToolExecutionReport,
    ToolSpec,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.ports import ReasoningEngine

MAX_QUERY_TOOL_CALLS = 3
MAX_QUERY_EVIDENCE_ITEMS = 8
MAX_ANSWER_BYTES = 32 * 1024
MAX_ANSWER_CHARS = 16_384
_TRUNCATION_WORD = re.compile(r"(?:trunc|l[ií]mit|parcial|primer)", re.IGNORECASE)

ReportLoader = Callable[[], ToolExecutionReport]


class QueryTurnError(RuntimeError):
    """Sanitized QUERY failure safe for the authenticated Odoo boundary."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class QueryService:
    """Reason only through QUERY tools and validate every result citation."""

    def __init__(
        self,
        *,
        reasoning_engine: ReasoningEngine,
        query_tools: Sequence[ToolSpec],
        report_loader: ReportLoader = lambda: ToolExecutionReport(),
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(instance_id="unknown"),
        trace_writer: TraceWriter = lambda trace_id, events: None,
        clock: Clock | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._query_tools = tuple(ToolSpec.model_validate(tool) for tool in query_tools)
        self._report_loader = report_loader
        self._instance_loader = instance_loader
        self._trace_writer = trace_writer
        self._clock = clock or _utc_now

    async def run(self, request: QueryTurnRequest) -> QueryTurnResponse:
        started = time.monotonic()
        events: list[TraceEventData] = []
        report_taken = False
        self._event(events, "turn.started", "ok", {"turn_id": str(request.turn_id)})
        try:
            now = self._validated_now()
            validate_query_turn_request(request, now=now)
            instance = self._safe_instance_summary()
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                workflow_hint=Workflow.QUERY,
                instance=instance,
                conversation_state=ConversationState(current_screen=request.screen),
                limits=TurnLimits(
                    max_tool_calls=MAX_QUERY_TOOL_CALLS,
                    max_evidence_items=MAX_QUERY_EVIDENCE_ITEMS,
                ),
            )
            self._event(
                events,
                "context.prepared",
                "ok",
                {
                    "instance_state": (
                        "unknown" if instance.instance_id == "unknown" else "detected"
                    ),
                    "model": request.screen.model,
                    "workflow": Workflow.QUERY.value,
                },
            )
            self._event(
                events,
                "reasoning.started",
                "ok",
                {"tool_count": len(self._query_tools), "workflow": "QUERY"},
            )
            answer = await self._reasoning_engine.run_turn(
                context,
                list(self._query_tools),
                AnswerEnvelope.model_json_schema(),
            )
            report = self._report_loader()
            report_taken = True
            self._append_tool_report(events, report)
            self._event(events, "reasoning.completed", "ok", {"workflow": "QUERY"})
            validated, citations = _validated_answer(
                answer,
                retrieved=report.retrieved_evidence,
                screen_model=cast(str, request.screen.model),
            )
            self._event(
                events,
                "answer.validated",
                "ok",
                {
                    "citation_count": len(citations),
                    "confidence": validated.confidence.value,
                    "workflow": "QUERY",
                },
            )
            response = QueryTurnResponse(
                turn_id=request.turn_id,
                answer_markdown=validated.answer_markdown,
                confidence=validated.confidence,
                limitations=tuple(validated.limitations),
                citations=citations,
                completed_at=self._validated_now(),
            )
            _reject_secret(response, request.delegation_token.get_secret_value())
            self._event(
                events,
                "turn.completed",
                "ok",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "workflow": "QUERY",
                },
            )
            return response
        except QueryTurnError as error:
            self._error_event(events, error.code, started)
            raise
        except ContextReadError as error:
            self._error_event(events, error.code, started)
            raise QueryTurnError(error.code, error.status_code) from None
        except Exception as error:
            code, status = _query_failure(error)
            self._error_event(events, code, started)
            raise QueryTurnError(code, status) from None
        finally:
            if not report_taken:
                try:
                    self._append_tool_report(events, self._report_loader())
                except Exception:
                    pass
            try:
                self._trace_writer(request.turn_id, tuple(events))
            except Exception:
                pass

    def _validated_now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise QueryTurnError("clock_unavailable", 503)
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
    def _append_tool_report(cls, events: list[TraceEventData], report: ToolExecutionReport) -> None:
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
    def _error_event(cls, events: list[TraceEventData], code: str, started: float) -> None:
        if any(event.event_name == "reasoning.started" for event in events) and not any(
            event.event_name == "reasoning.completed" for event in events
        ):
            cls._event(
                events,
                "reasoning.completed",
                "error",
                {"error_code": code, "workflow": "QUERY"},
            )
        cls._event(
            events,
            "turn.completed",
            "error",
            {
                "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                "error_code": code,
                "workflow": "QUERY",
            },
        )


def _validated_answer(
    answer: AnswerEnvelope,
    *,
    retrieved: Sequence[Evidence],
    screen_model: str,
) -> tuple[AnswerEnvelope, tuple[QueryCitation, ...]]:
    if answer.workflow is not Workflow.QUERY:
        raise QueryTurnError("answer_workflow_invalid", 502)
    if answer.proposed_action is not None:
        raise QueryTurnError("answer_action_not_allowed", 502)
    if (
        not answer.answer_markdown
        or len(answer.answer_markdown) > MAX_ANSWER_CHARS
        or len(answer.answer_markdown.encode("utf-8")) > MAX_ANSWER_BYTES
    ):
        raise QueryTurnError("answer_invalid", 502)
    limitations = tuple(dict.fromkeys(answer.limitations))
    if len(limitations) > 8 or any(not value or len(value) > 1_024 for value in limitations):
        raise QueryTurnError("answer_invalid", 502)
    references = tuple(dict.fromkeys(answer.evidence_refs))
    if not references:
        raise QueryTurnError("query_evidence_required", 502)
    by_id: dict[UUID, Evidence] = {}
    canonical: dict[UUID, str] = {}
    for evidence in retrieved:
        value = evidence.model_dump_json()
        if evidence.evidence_id in canonical and canonical[evidence.evidence_id] != value:
            raise QueryTurnError("evidence_duplicate_conflict", 502)
        canonical[evidence.evidence_id] = value
        by_id[evidence.evidence_id] = evidence
    try:
        cited = tuple(by_id[reference] for reference in references)
    except KeyError:
        raise QueryTurnError("evidence_ref_unknown", 502) from None
    if any(evidence.status is not EvidenceStatus.CHECKED for evidence in cited):
        raise QueryTurnError("evidence_not_checked", 502)
    citations = tuple(_citation(evidence, screen_model=screen_model) for evidence in cited)
    if any(citation.truncated for citation in citations) and not any(
        _TRUNCATION_WORD.search(value) for value in limitations
    ):
        raise QueryTurnError("answer_truncation_unacknowledged", 502)
    return (
        answer.model_copy(
            update={
                "evidence_refs": list(references),
                "limitations": list(limitations),
            }
        ),
        citations,
    )


def _citation(evidence: Evidence, *, screen_model: str) -> QueryCitation:
    pointer = evidence.pointer
    if (
        evidence.kind is not EvidenceKind.RECORD
        or evidence.observed_at is None
        or not isinstance(pointer, dict)
        or pointer.get("provider") != "odoo_query"
        or pointer.get("model") != screen_model
        or pointer.get("operation") not in {"query_records", "aggregate_records"}
    ):
        raise QueryTurnError("query_citation_invalid", 502)
    operation = cast(Literal["query_records", "aggregate_records"], pointer["operation"])
    try:
        if operation == "query_records":
            record_result = QueryRecordsResult.model_validate(evidence.payload)
            returned_count = record_result.returned_count
            limit = record_result.limit
            empty = returned_count == 0
            result_model = record_result.model
            result_captured_at = record_result.captured_at
            truncated = record_result.truncated
        else:
            aggregate = AggregateRecordsResult.model_validate(evidence.payload)
            returned_count = aggregate.returned_group_count
            limit = aggregate.group_limit
            empty = _aggregate_empty(aggregate)
            result_model = aggregate.model
            result_captured_at = aggregate.captured_at
            truncated = aggregate.truncated
    except ValueError:
        raise QueryTurnError("query_citation_invalid", 502) from None
    if result_model != screen_model or result_captured_at != evidence.observed_at:
        raise QueryTurnError("query_citation_invalid", 502)
    return QueryCitation(
        evidence_id=evidence.evidence_id,
        model=screen_model,
        operation=operation,
        captured_at=evidence.observed_at,
        returned_count=returned_count,
        limit=limit,
        truncated=truncated,
        empty=empty,
    )


def _aggregate_empty(result: AggregateRecordsResult) -> bool:
    if not result.groups:
        return True
    if result.query.group_by:
        return False
    counts = [
        metric.value for metric in result.groups[0].metrics if metric.operation.value == "count"
    ]
    return bool(counts) and counts == [0]


def _reject_secret(response: QueryTurnResponse, secret: str) -> None:
    if secret and secret in response.model_dump_json():
        raise QueryTurnError("unsafe_response", 502)


def _query_failure(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", "engine_unavailable")
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if "budget" in code:
        return "query_budget_exceeded", 502
    if "timeout" in code or "deadline" in code:
        return "engine_timeout", 504
    if code.startswith("query_") or code in {
        "aggregate_not_allowed",
        "codex_proposed_action_not_allowed",
        "field_not_in_schema",
        "field_not_groupable",
        "field_not_sortable",
        "operator_not_allowed",
        "schema_binding_invalid",
        "tool_input_invalid",
    }:
        return "query_rejected", 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    return "engine_unavailable", 503


def _utc_now() -> datetime:
    return datetime.now(UTC)
