"""Validate a provider interpretation before Odoo grants workflow authority."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from odoo_ai.contracts.chat import (
    ChatRouteDecision,
    ChatRouteRequest,
    ChatRouteResponse,
    ChatRouteWorkflow,
)
from odoo_ai.ports.chat_routing import (
    ChatRoutingInterpreter,
    ChatRoutingInterpreterError,
)

HistoryLoader = Callable[[ChatRouteRequest], Awaitable[str]]


class ChatRoutingError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class ChatRoutingService:
    """Keep linguistic freedom separate from the host's bounded authority decision."""

    def __init__(
        self,
        *,
        interpreter: ChatRoutingInterpreter,
        history_loader: HistoryLoader,
    ) -> None:
        self._interpreter = interpreter
        self._history_loader = history_loader

    async def run(self, request: ChatRouteRequest) -> ChatRouteResponse:
        history = await self._history_loader(request)
        try:
            decision = await self._interpreter.interpret(
                request,
                recent_history=history,
            )
        except ChatRoutingInterpreterError as error:
            raise ChatRoutingError(_engine_code(error.code)) from None
        _validate_decision(request, decision)
        return ChatRouteResponse(
            turn_id=request.turn_id,
            workflow=decision.workflow,
            target_model=decision.target_model,
            resolved_message=decision.resolved_message,
        )


def _validate_decision(
    request: ChatRouteRequest,
    decision: ChatRouteDecision,
) -> None:
    allowed_models = {candidate.model for candidate in request.candidates}
    target = decision.target_model
    if target is not None and target not in allowed_models:
        raise ChatRoutingError("invalid_response", 502)
    if decision.workflow is ChatRouteWorkflow.QUERY:
        if target is None:
            raise ChatRoutingError("invalid_response", 502)
        return
    if decision.workflow in {ChatRouteWorkflow.ACTION, ChatRouteWorkflow.EXPLAIN}:
        if (
            not request.has_current_record
            or target is None
            or target != request.current_model
        ):
            raise ChatRoutingError("invalid_response", 502)
        return
    if decision.workflow is ChatRouteWorkflow.HOW_TO:
        return
    if decision.workflow is ChatRouteWorkflow.GENERAL and target is None:
        return
    raise ChatRoutingError("invalid_response", 502)


def _engine_code(code: str) -> str:
    if "timeout" in code or "deadline" in code:
        return "engine_timeout"
    return "engine_unavailable"
