import asyncio
from uuid import uuid4

import pytest

from odoo_ai.application.chat_routing import ChatRoutingError, ChatRoutingService
from odoo_ai.contracts.chat import (
    ChatActor,
    ChatRouteCandidate,
    ChatRouteDecision,
    ChatRouteRequest,
)


class StubInterpreter:
    def __init__(self, decision: ChatRouteDecision) -> None:
        self.decision = decision
        self.history: str | None = None

    async def interpret(
        self,
        request: ChatRouteRequest,
        *,
        recent_history: str,
    ) -> ChatRouteDecision:
        del request
        self.history = recent_history
        return self.decision


def _request() -> ChatRouteRequest:
    return ChatRouteRequest(
        turn_id=uuid4(),
        actor=ChatActor(database="test", uid=7),
        message="請列出逾期發票最多的客戶",
        current_model="sale.order",
        has_current_record=True,
        user_language="zh_TW",
        candidates=(
            ChatRouteCandidate(model="sale.order", labels=("Sales / Orders",)),
            ChatRouteCandidate(
                model="account.move",
                labels=("Invoicing / Customers / Invoices",),
            ),
        ),
    )


def test_multilingual_interpretation_can_select_a_different_allowed_model() -> None:
    interpreter = StubInterpreter(
        ChatRouteDecision(
            workflow="QUERY",
            target_model="account.move",
            resolved_message="請列出逾期發票最多的客戶",
        )
    )

    async def history_loader(request: ChatRouteRequest) -> str:
        del request
        return "Usuario: antes preguntó por pedidos"

    service = ChatRoutingService(
        interpreter=interpreter,
        history_loader=history_loader,
    )
    response = asyncio.run(service.run(_request()))

    assert response.workflow == "QUERY"
    assert response.target_model == "account.move"
    assert response.resolved_message == "請列出逾期發票最多的客戶"
    assert interpreter.history == "Usuario: antes preguntó por pedidos"


def test_interpreter_cannot_select_a_model_outside_the_host_allowlist() -> None:
    interpreter = StubInterpreter(
        ChatRouteDecision(
            workflow="QUERY",
            target_model="res.users",
            resolved_message="請列出逾期發票最多的客戶",
        )
    )

    async def history_loader(request: ChatRouteRequest) -> str:
        del request
        return ""

    service = ChatRoutingService(
        interpreter=interpreter,
        history_loader=history_loader,
    )

    with pytest.raises(ChatRoutingError, match="invalid_response"):
        asyncio.run(service.run(_request()))


def test_action_interpretation_cannot_escape_the_concrete_current_record_model() -> None:
    interpreter = StubInterpreter(
        ChatRouteDecision(
            workflow="ACTION",
            target_model="account.move",
            resolved_message="請列出逾期發票最多的客戶",
        )
    )

    async def history_loader(request: ChatRouteRequest) -> str:
        del request
        return ""

    service = ChatRoutingService(
        interpreter=interpreter,
        history_loader=history_loader,
    )

    with pytest.raises(ChatRoutingError, match="invalid_response"):
        asyncio.run(service.run(_request()))
