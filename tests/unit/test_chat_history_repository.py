from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from odoo_ai.contracts.chat import ChatActor
from odoo_ai.storage.chat_repository import load_chat_history

CONVERSATION_ID = UUID("12345678-1234-5678-9234-567812345678")


def _conversation():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=CONVERSATION_ID,
        title="Facturas vencidas",
        created_at=now,
        updated_at=now,
    )


def test_history_landing_lists_conversations_without_loading_messages() -> None:
    session = MagicMock()
    session.scalars.return_value = (_conversation(),)

    result = load_chat_history(
        session,
        actor=ChatActor(database="customer", uid=7),
        conversation_id=None,
        max_messages=40,
    )

    assert [item.conversation_id for item in result.conversations] == [CONVERSATION_ID]
    assert result.active_conversation_id is None
    assert result.messages == ()
    assert session.scalars.call_count == 1


def test_selected_conversation_loads_only_its_bounded_messages() -> None:
    conversation = _conversation()
    message = SimpleNamespace(
        id=uuid4(),
        role="user",
        content="¿Qué facturas están vencidas?",
        created_at=datetime.now(UTC),
    )
    session = MagicMock()
    session.scalars.side_effect = [(conversation,), (message,)]

    result = load_chat_history(
        session,
        actor=ChatActor(database="customer", uid=7),
        conversation_id=CONVERSATION_ID,
        max_messages=20,
    )

    assert result.active_conversation_id == CONVERSATION_ID
    assert len(result.messages) == 1
    assert result.messages[0].content == message.content
    assert session.scalars.call_count == 2
