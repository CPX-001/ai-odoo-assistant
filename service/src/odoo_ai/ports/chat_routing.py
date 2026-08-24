"""Provider-neutral natural-language interpretation boundary for product chat."""

from typing import Protocol

from odoo_ai.contracts.chat import ChatRouteDecision, ChatRouteRequest


class ChatRoutingInterpreterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ChatRoutingInterpreter(Protocol):
    async def interpret(
        self,
        request: ChatRouteRequest,
        *,
        recent_history: str,
    ) -> ChatRouteDecision: ...
