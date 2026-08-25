from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from odoo_ai.contracts.chat import ChatActor
from odoo_ai.storage.chat_repository import recent_chat_text


def test_recent_chat_text_keeps_newest_messages_when_char_budget_is_tight() -> None:
    conversation_id = uuid4()
    newest = (
        SimpleNamespace(role="assistant", content="latest answer"),
        SimpleNamespace(role="user", content="latest question"),
        SimpleNamespace(role="assistant", content="old context that should be dropped"),
    )
    session = MagicMock()
    session.scalar.return_value = conversation_id
    session.scalars.return_value = newest

    result = recent_chat_text(
        session,
        actor=ChatActor(database="customer", uid=7),
        conversation_id=conversation_id,
        max_messages=8,
        max_chars=45,
    )

    assert "old context" not in result
    assert result.endswith("Assistant: latest answer")
    assert "User: latest question" in result
