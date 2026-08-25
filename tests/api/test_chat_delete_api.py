import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from odoo_ai.api import create_app
from odoo_ai.contracts.chat_delete import ChatDeleteRequest, ChatDeleteResponse
from odoo_ai.runtime.chat_delete import RuntimeChatDeleteService

SECRET = "chat-delete-secret-" + "s" * 40
FIRST_ID = UUID("12345678-1234-5678-9234-567812345678")
SECOND_ID = UUID("22345678-1234-5678-9234-567812345678")


class StubDeleteService(RuntimeChatDeleteService):
    def __init__(self) -> None:
        self.request: ChatDeleteRequest | None = None

    async def delete(self, request: ChatDeleteRequest) -> ChatDeleteResponse:
        self.request = request
        return ChatDeleteResponse(deleted_count=len(request.conversation_ids))


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


async def _post(payload: object, *, secret: str | None = SECRET):
    service = StubDeleteService()
    app = create_app(chat_delete_service=service)
    headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/delete", json=payload, headers=headers)
    return response, service


def test_chat_delete_requires_machine_auth() -> None:
    payload = {
        "actor": {"database": "customer", "uid": 7},
        "conversation_ids": [str(FIRST_ID)],
    }
    response, _ = asyncio.run(_post(payload, secret=None))
    assert response.status_code == 401


def test_chat_delete_passes_actor_and_bounded_ids_to_service() -> None:
    payload = {
        "actor": {"database": "customer", "uid": 7},
        "conversation_ids": [str(FIRST_ID), str(SECOND_ID)],
    }
    response, service = asyncio.run(_post(payload))

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 2}
    assert service.request is not None
    assert service.request.actor.database == "customer"
    assert service.request.actor.uid == 7
    assert service.request.conversation_ids == (FIRST_ID, SECOND_ID)


def test_chat_delete_rejects_duplicate_ids() -> None:
    payload = {
        "actor": {"database": "customer", "uid": 7},
        "conversation_ids": [str(FIRST_ID), str(FIRST_ID)],
    }
    response, service = asyncio.run(_post(payload))

    assert response.status_code == 422
    assert service.request is None
