from unittest.mock import MagicMock
from uuid import UUID

import pytest

from odoo_ai.contracts.chat import ChatActor
from odoo_ai.storage.chat_delete_repository import delete_chat_conversations
from odoo_ai.storage.chat_repository import ChatStoreError

FIRST_ID = UUID("12345678-1234-5678-9234-567812345678")
SECOND_ID = UUID("22345678-1234-5678-9234-567812345678")


def test_delete_conversations_requires_all_ids_to_belong_to_actor() -> None:
    session = MagicMock()
    session.scalars.return_value = (FIRST_ID,)

    with pytest.raises(ChatStoreError) as captured:
        delete_chat_conversations(
            session,
            actor=ChatActor(database="customer", uid=7),
            conversation_ids=(FIRST_ID, SECOND_ID),
        )

    assert captured.value.code == "conversation_not_found"
    session.execute.assert_not_called()


def test_delete_conversations_executes_once_after_ownership_check() -> None:
    session = MagicMock()
    session.scalars.return_value = (FIRST_ID, SECOND_ID)

    result = delete_chat_conversations(
        session,
        actor=ChatActor(database="customer", uid=7),
        conversation_ids=(FIRST_ID, SECOND_ID),
    )

    assert result.deleted_count == 2
    session.execute.assert_called_once()
    session.flush.assert_called_once()
