"""Bounded deletion operations for Assistant chat history."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.chat_delete import ChatDeleteResponse
from odoo_ai.storage.chat_models import ChatConversation
from odoo_ai.storage.chat_repository import ChatStoreError


def delete_chat_conversations(
    session: Session,
    *,
    actor: ChatActor,
    conversation_ids: tuple[UUID, ...],
) -> ChatDeleteResponse:
    requested = tuple(dict.fromkeys(conversation_ids))
    if not requested or len(requested) != len(conversation_ids):
        raise ChatStoreError("conversation_not_found")

    owned_ids = set(
        session.scalars(
            select(ChatConversation.id).where(
                ChatConversation.id.in_(requested),
                ChatConversation.database == actor.database,
                ChatConversation.uid == actor.uid,
            )
        )
    )
    if owned_ids != set(requested):
        raise ChatStoreError("conversation_not_found")

    session.execute(
        delete(ChatConversation).where(
            ChatConversation.id.in_(requested),
            ChatConversation.database == actor.database,
            ChatConversation.uid == actor.uid,
        )
    )
    session.flush()
    return ChatDeleteResponse(deleted_count=len(requested))
