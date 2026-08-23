"""Evidence-led orchestration for the preview-only ACTION reasoning workflow."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from odoo_ai.application.context_read import (
    Clock,
    ContextReadError,
    InstanceLoader,
    TraceEventData,
    TraceWriter,
    validate_context_turn_request,
)
from odoo_ai.contracts import (
    ActionProposalHandle,
    ActionToolReport,
    ActionTurnRequest,
    ActionTurnResponse,
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceStatus,
    InstanceProfileSummary,
    ToolSpec,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.ports import ReasoningEngine

MAX_ACTION_TOOL_CALLS = 2
MAX_ACTION_EVIDENCE_ITEMS = 8
MAX_ANSWER_BYTES = 32 * 1024
MAX_ANSWER_CHARS = 16_384

ActionReportLoader = Callable[[], ActionToolReport]


class ActionTurnError(RuntimeError):
    """Sanitized ACTION failure safe for the authenticated Odoo boundary."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ActionService:
    """Let the engine request a preview, then reconcile only host-produced facts."""

    def __init__(
        self,
        *,
        reasoning_engine: ReasoningEngine,
        action_tools: Sequence[ToolSpec],
        report_loader: ActionReportLoader = lambda: ActionToolReport(),
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(instance_id="unknown"),
        trace_writer: TraceWriter = lambda trace_id, events: None,
        clock: Clock | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._action_tools = tuple(ToolSpec.model_validate(tool) for tool in action_tools)
        self._report_loader = report_loader
        self._instance_loader = instance_loader
        self._trace_writer = trace_writer
        self._clock = clock or _utc_now

    async def run(self, request: ActionTurnRequest) -> ActionTurnResponse:
        started = time.monotonic()
        events: list[TraceEventData] = []
        report_taken = False
        self._event(events, "turn.started", "ok", {"turn_id": str(request.turn_id)})
        try:
            now = self._validated_now()
            validate_context_turn_request(request, now=now)
            if request.user.allowed_company_ids != sorted(
                request.user.allowed_company_ids
            ):
                raise ActionTurnError("invalid_user_context", 422)
            instance = self._safe_instance_summary()
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                workflow_hint=Workflow.ACTION,
                instance=instance,
                conversation_state=ConversationState(current_screen=request.screen),
                limits=TurnLimits(
                    max_tool_calls=MAX_ACTION_TOOL_CALLS,
                    max_evidence_items=MAX_ACTION_EVIDENCE_ITEMS,
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
                    "workflow": Workflow.ACTION.value,
                },
            )
            self._event(
                events,
                "reasoning.started",
                "ok",
                {"tool_count": len(self._action_tools), "workflow": "ACTION"},
            )
            answer = await self._reasoning_engine.run_turn(
                context,
                list(self._action_tools),
                AnswerEnvelope.model_json_schema(),
            )
            report = self._report_loader()
            report_taken = True
            self._append_tool_report(events, report)
            self._event(events, "reasoning.completed", "ok", {"workflow": "ACTION"})
            validated, proposal, references = _validated_answer(
                answer,
                report=report,
                turn_id=request.turn_id,
                model=request.screen.model or "",
                record_id=request.screen.res_id or 0,
            )
            response = ActionTurnResponse(
                turn_id=request.turn_id,
                answer_markdown=validated.answer_markdown,
                confidence=validated.confidence,
                limitations=tuple(validated.limitations),
                evidence_refs=references,
                proposal=proposal,
                completed_at=self._validated_now(),
            )
            if request.delegation_token.get_secret_value() in response.model_dump_json():
                raise ActionTurnError("unsafe_response", 502)
            self._event(
                events,
                "turn.completed",
                "ok",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "proposal_created": proposal is not None,
                    "workflow": "ACTION",
                },
            )
            return response
        except ActionTurnError as error:
            self._error_event(events, error.code, started)
            raise
        except ContextReadError as error:
            self._error_event(events, error.code, started)
            raise ActionTurnError(error.code, error.status_code) from None
        except Exception as error:
            code, status = _action_failure(error)
            self._error_event(events, code, started)
            raise ActionTurnError(code, status) from None
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
            raise ActionTurnError("clock_unavailable", 503)
        return now.astimezone(UTC)

    def _safe_instance_summary(self) -> InstanceProfileSummary:
        try:
            value = self._instance_loader()
        except Exception:
            return InstanceProfileSummary(instance_id="unknown")
        return (
            value
            if isinstance(value, InstanceProfileSummary)
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
        cls, events: list[TraceEventData], report: ActionToolReport
    ) -> None:
        for event in report.tool_report.events:
            cls._event(events, event.event_name, event.status, event.attributes)
        for evidence in report.tool_report.retrieved_evidence:
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
        cls, events: list[TraceEventData], code: str, started: float
    ) -> None:
        if any(item.event_name == "reasoning.started" for item in events) and not any(
            item.event_name == "reasoning.completed" for item in events
        ):
            cls._event(
                events,
                "reasoning.completed",
                "error",
                {"error_code": code, "workflow": "ACTION"},
            )
        cls._event(
            events,
            "turn.completed",
            "error",
            {
                "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                "error_code": code,
                "workflow": "ACTION",
            },
        )


def _validated_answer(
    answer: AnswerEnvelope,
    *,
    report: ActionToolReport,
    turn_id: UUID,
    model: str,
    record_id: int,
) -> tuple[AnswerEnvelope, ActionProposalHandle | None, tuple[UUID, ...]]:
    if answer.workflow is not Workflow.ACTION:
        raise ActionTurnError("answer_workflow_invalid", 502)
    if (
        not answer.answer_markdown
        or len(answer.answer_markdown) > MAX_ANSWER_CHARS
        or len(answer.answer_markdown.encode("utf-8")) > MAX_ANSWER_BYTES
    ):
        raise ActionTurnError("answer_invalid", 502)
    limitations = tuple(dict.fromkeys(answer.limitations))
    if len(limitations) > 8 or any(not value or len(value) > 1_024 for value in limitations):
        raise ActionTurnError("answer_invalid", 502)
    references = tuple(dict.fromkeys(answer.evidence_refs))
    evidence = _evidence_by_id(report.tool_report.retrieved_evidence)
    if any(reference not in evidence for reference in references):
        raise ActionTurnError("evidence_ref_unknown", 502)
    if any(evidence[reference].status is not EvidenceStatus.CHECKED for reference in references):
        raise ActionTurnError("evidence_not_checked", 502)
    if len(report.proposals) > 1:
        raise ActionTurnError("action_proposal_ambiguous", 502)
    proposal = report.proposals[0] if report.proposals else None
    presentation = answer.proposed_action
    if proposal is None:
        if presentation is not None:
            raise ActionTurnError("action_proposal_not_produced", 502)
        if answer.confidence is not AnswerConfidence.LOW or not limitations:
            raise ActionTurnError("action_preview_required", 502)
        return (
            answer.model_copy(update={"limitations": list(limitations)}),
            None,
            references,
        )
    if (
        proposal.turn_id != turn_id
        or proposal.target.model != model
        or proposal.target.record_id != record_id
        or presentation is None
        or presentation.action_type != "record_patch"
        or set(presentation.details) != {"payload_fingerprint", "proposal_id"}
        or presentation.details.get("proposal_id") != str(proposal.proposal_id)
        or presentation.details.get("payload_fingerprint") != proposal.payload_fingerprint
        or proposal.evidence_id not in references
    ):
        raise ActionTurnError("action_proposal_mismatch", 502)
    preview_evidence = evidence.get(proposal.evidence_id)
    pointer = preview_evidence.pointer if preview_evidence is not None else None
    if (
        preview_evidence is None
        or not isinstance(pointer, dict)
        or pointer.get("provider") != "odoo_action_preview"
        or pointer.get("proposal_id") != str(proposal.proposal_id)
    ):
        raise ActionTurnError("action_evidence_invalid", 502)
    return (
        answer.model_copy(update={"limitations": list(limitations)}),
        proposal,
        references,
    )


def _evidence_by_id(values: Sequence[Evidence]) -> dict[UUID, Evidence]:
    result: dict[UUID, Evidence] = {}
    canonical: dict[UUID, str] = {}
    for evidence in values:
        serialized = evidence.model_dump_json()
        if evidence.evidence_id in canonical and canonical[evidence.evidence_id] != serialized:
            raise ActionTurnError("evidence_duplicate_conflict", 502)
        canonical[evidence.evidence_id] = serialized
        result[evidence.evidence_id] = evidence
    return result


def _action_failure(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", "engine_unavailable")
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if "timeout" in code or "deadline" in code:
        return "engine_timeout", 504
    if "budget" in code:
        return "action_budget_exceeded", 502
    if code in {
        "action_context_mismatch",
        "action_target_not_allowed",
        "action_tool_not_allowlisted",
        "field_not_write_eligible",
        "payload_fingerprint_mismatch",
        "tool_input_invalid",
        "write_schema_mismatch",
    }:
        return "action_rejected", 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    return "engine_unavailable", 503


def _utc_now() -> datetime:
    return datetime.now(UTC)
