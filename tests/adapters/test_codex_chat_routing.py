import asyncio
import json
from uuid import uuid4

import pytest

from odoo_ai.adapters.chat_routing import CodexChatRoutingInterpreter
from odoo_ai.contracts.chat import (
    ChatActor,
    ChatRouteCandidate,
    ChatRouteRequest,
)
from odoo_ai.ports.chat_routing import ChatRoutingInterpreterError


class StubStructuredEngine:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.input_text: str | None = None

    async def run_structured_output(
        self,
        *,
        instructions: str,
        input_text: str,
        output_schema: dict[str, object],
    ) -> dict[str, object]:
        assert "multilingual" in instructions
        assert output_schema["additionalProperties"] is False
        self.input_text = input_text
        return self.result


def _request() -> ChatRouteRequest:
    return ChatRouteRequest(
        turn_id=uuid4(),
        actor=ChatActor(database="test", uid=9),
        message="Welche Rechnungen sind überfällig?",
        current_model="sale.order",
        has_current_record=True,
        user_language="de_DE",
        candidates=(
            ChatRouteCandidate(model="sale.order", labels=("Sales / Orders",)),
            ChatRouteCandidate(model="account.move", labels=("Invoices",)),
        ),
    )


def test_codex_interpreter_serializes_untrusted_multilingual_context() -> None:
    engine = StubStructuredEngine(
        {
            "workflow": "QUERY",
            "target_model": "account.move",
            "resolved_message": "Welche Rechnungen sind überfällig?",
        }
    )
    interpreter = CodexChatRoutingInterpreter(engine)  # type: ignore[arg-type]

    decision = asyncio.run(
        interpreter.interpret(_request(), recent_history="previous context")
    )

    assert decision.workflow == "QUERY"
    assert decision.target_model == "account.move"
    assert decision.resolved_message == "Welche Rechnungen sind überfällig?"
    assert engine.input_text is not None
    payload = json.loads(engine.input_text)
    assert payload["host_contract"]["authority_granted"] is False
    assert payload["untrusted_data"]["message"].startswith("Welche")


def test_codex_interpreter_rejects_an_invalid_structured_decision() -> None:
    engine = StubStructuredEngine(
        {
            "workflow": "QUERY",
            "target_model": 42,
            "resolved_message": "Welche Rechnungen sind überfällig?",
        }
    )
    interpreter = CodexChatRoutingInterpreter(engine)  # type: ignore[arg-type]

    with pytest.raises(ChatRoutingInterpreterError, match="codex_answer_invalid"):
        asyncio.run(interpreter.interpret(_request(), recent_history=""))
