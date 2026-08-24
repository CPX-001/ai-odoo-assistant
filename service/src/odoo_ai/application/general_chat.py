"""Provider-neutral orchestration for the read-only general chat workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    InstanceProfileSummary,
    ToolSpec,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.contracts.chat import GeneralTurnRequest, GeneralTurnResponse
from odoo_ai.ports.reasoning import ReasoningEngine, ReasoningEngineError

_GENERAL_MAX_TOOL_CALLS = 8
_GENERAL_MAX_EVIDENCE = 16

HistoryLoader = Callable[[GeneralTurnRequest], Awaitable[str]]
KnowledgeLoader = Callable[[GeneralTurnRequest], Awaitable[tuple[Evidence, ...]]]


class GeneralChatError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class GeneralChatService:
    """Give a reasoning engine broad read context without broad Odoo authority."""

    def __init__(
        self,
        *,
        reasoning_engine: ReasoningEngine,
        history_loader: HistoryLoader,
        knowledge_loader: KnowledgeLoader,
        tools: Sequence[ToolSpec] = (),
        fallback_engine: ReasoningEngine | None = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._history_loader = history_loader
        self._knowledge_loader = knowledge_loader
        self._tools = tuple(tools)
        self._fallback_engine = fallback_engine

    async def run(self, request: GeneralTurnRequest) -> GeneralTurnResponse:
        history, knowledge = await asyncio.gather(
            self._history_loader(request),
            self._knowledge_loader(request),
        )
        context = ContextPack(
            request=UserRequest(message=request.message),
            screen=request.screen,
            user=request.user,
            workflow_hint=None,
            instance=InstanceProfileSummary(instance_id=f"odoo:{request.actor.database}"),
            retrieved_evidence=list(knowledge),
            conversation_state=ConversationState(
                current_screen=request.screen,
                short_summary=history,
            ),
            limits=TurnLimits(
                max_tool_calls=_GENERAL_MAX_TOOL_CALLS,
                max_evidence_items=_GENERAL_MAX_EVIDENCE,
            ),
        )

        try:
            answer = await self._reasoning_engine.run_turn(
                context,
                list(self._tools),
                AnswerEnvelope.model_json_schema(),
            )
        except ReasoningEngineError as error:
            if not (
                error.code.startswith("source_") and self._fallback_engine is not None
            ):
                raise GeneralChatError(_engine_code(error.code)) from None
            answer = await self._run_fallback(context)

        if answer.workflow is Workflow.ACTION or answer.proposed_action is not None:
            raise GeneralChatError("invalid_response", 502)
        if len(answer.answer_markdown) > 16_384:
            raise GeneralChatError("invalid_response", 502)
        return GeneralTurnResponse(
            turn_id=request.turn_id,
            workflow=answer.workflow,
            answer_markdown=answer.answer_markdown,
            confidence=answer.confidence,
            limitations=tuple(answer.limitations),
            evidence_refs=tuple(answer.evidence_refs),
            completed_at=datetime.now(UTC),
        )

    async def _run_fallback(self, context: ContextPack) -> AnswerEnvelope:
        if self._fallback_engine is None:
            raise GeneralChatError("engine_unavailable")
        try:
            return await self._fallback_engine.run_turn(
                context,
                [],
                AnswerEnvelope.model_json_schema(),
            )
        except ReasoningEngineError as error:
            raise GeneralChatError(_engine_code(error.code)) from None


def _engine_code(code: str) -> str:
    if "timeout" in code or "deadline" in code:
        return "engine_timeout"
    return "engine_unavailable"
