import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from odoo_ai.api import create_app
from odoo_ai.application.general_chat import GeneralChatService
from odoo_ai.contracts.chat import (
    ChatAppendRequest,
    ChatAppendResponse,
    ChatConversationView,
    ChatHistoryRequest,
    ChatHistoryResponse,
    ChatMessageView,
    GeneralTurnRequest,
    GeneralTurnResponse,
)
from odoo_ai.runtime.chat import RuntimeChatHistoryService

SECRET = "chat-secret-" + "s" * 48
CONVERSATION_ID = UUID("12345678-1234-5678-9234-567812345678")


class StubHistoryService(RuntimeChatHistoryService):
    def __init__(self) -> None:
        self.appended: ChatAppendRequest | None = None

    async def history(self, request: ChatHistoryRequest) -> ChatHistoryResponse:
        del request
        now = datetime.now(UTC)
        return ChatHistoryResponse(
            conversations=(
                ChatConversationView(
                    conversation_id=CONVERSATION_ID,
                    title="Facturas vencidas",
                    created_at=now,
                    updated_at=now,
                ),
            ),
            active_conversation_id=CONVERSATION_ID,
            messages=(
                ChatMessageView(
                    message_id=uuid4(),
                    role="user",
                    content="¿Qué facturas están vencidas?",
                    created_at=now,
                ),
            ),
        )

    async def append(self, request: ChatAppendRequest) -> ChatAppendResponse:
        self.appended = request
        return ChatAppendResponse(conversation_id=CONVERSATION_ID, created=True)


class StubGeneralService(GeneralChatService):
    def __init__(self) -> None:
        self.request: GeneralTurnRequest | None = None

    async def run(self, request: GeneralTurnRequest) -> GeneralTurnResponse:
        self.request = request
        return GeneralTurnResponse(
            turn_id=request.turn_id,
            workflow="EXPLAIN",
            answer_markdown="Respuesta general",
            confidence="high",
            limitations=(),
            evidence_refs=(),
            completed_at=datetime.now(UTC),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


async def _post(path: str, payload: object, *, secret: str | None = SECRET):
    history = StubHistoryService()
    general = StubGeneralService()
    app = create_app(chat_history_service=history, general_chat_service=general)
    headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=payload, headers=headers)
    return response, history, general


def test_chat_history_requires_machine_auth() -> None:
    payload = {"actor": {"database": "customer", "uid": 7}}
    response, _, _ = asyncio.run(_post("/v1/chat/history", payload, secret=None))
    assert response.status_code == 401


def test_chat_history_is_scoped_by_odoo_actor() -> None:
    payload = {"actor": {"database": "customer", "uid": 7}}
    response, _, _ = asyncio.run(_post("/v1/chat/history", payload))
    assert response.status_code == 200
    assert response.json()["active_conversation_id"] == str(CONVERSATION_ID)
    assert response.json()["messages"][0]["role"] == "user"


def test_chat_append_persists_only_sanitized_exchange() -> None:
    payload = {
        "actor": {"database": "customer", "uid": 7},
        "conversation_id": None,
        "user_message": "Pregunta",
        "assistant_message": "Respuesta",
        "internal_workflow": "GENERAL",
    }
    response, history, _ = asyncio.run(_post("/v1/chat/append", payload))
    assert response.status_code == 200
    assert history.appended is not None
    assert history.appended.actor.uid == 7
    assert history.appended.internal_workflow == "GENERAL"


def test_general_turn_does_not_require_active_model_or_record() -> None:
    turn_id = str(uuid4())
    payload = {
        "turn_id": turn_id,
        "actor": {"database": "customer", "uid": 7},
        "conversation_id": None,
        "message": "Explícame cómo está implementado el módulo",
        "screen": {
            "action_id": None,
            "menu_id": None,
            "view_type": None,
            "model": None,
            "res_id": None,
            "selected_ids": [],
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat(),
        },
        "user": {
            "uid": 7,
            "company_id": 1,
            "allowed_company_ids": [1],
            "lang": "es_ES",
        },
    }
    response, _, general = asyncio.run(_post("/v1/turns/general", payload))
    assert response.status_code == 200
    assert response.json()["turn_id"] == turn_id
    assert general.request is not None
    assert general.request.screen.model is None
