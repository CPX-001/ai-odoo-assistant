"""Bounded persistence operations for Assistant chat history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from odoo_ai.contracts.chat import (
    ChatActor,
    ChatAppendResponse,
    ChatConversationView,
    ChatHistoryResponse,
    ChatMessageView,
)
from odoo_ai.storage.chat_models import ChatConversation, ChatMessage


class ChatStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_chat_history(
    session: Session,
    *,
    actor: ChatActor,
    conversation_id: UUID | None,
    max_conversations: int,
    max_messages: int,
) -> ChatHistoryResponse:
    conversations = tuple(
        session.scalars(
            select(ChatConversation)
            .where(
                ChatConversation.database == actor.database,
                ChatConversation.uid == actor.uid,
            )
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.created_at.desc())
            .limit(max_conversations)
        )
    )
    selected = None
    if conversation_id is not None:
        selected = next((item for item in conversations if item.id == conversation_id), None)
        if selected is None:
            selected = session.scalar(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.database == actor.database,
                    ChatConversation.uid == actor.uid,
                )
            )
        if selected is None:
            raise ChatStoreError("conversation_not_found")

    messages: tuple[ChatMessage, ...] = ()
    if selected is not None:
        newest = tuple(
            session.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == selected.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(max_messages)
            )
        )
        messages = tuple(reversed(newest))

    return ChatHistoryResponse(
        conversations=tuple(_conversation_view(item) for item in conversations),
        active_conversation_id=selected.id if selected is not None else None,
        messages=tuple(_message_view(item) for item in messages),
    )


def append_chat_exchange(
    session: Session,
    *,
    actor: ChatActor,
    conversation_id: UUID | None,
    user_message: str,
    assistant_message: str,
    internal_workflow: str,
) -> ChatAppendResponse:
    conversation = None
    created = False
    if conversation_id is not None:
        conversation = session.scalar(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.database == actor.database,
                ChatConversation.uid == actor.uid,
            )
        )
        if conversation is None:
            raise ChatStoreError("conversation_not_found")
    else:
        conversation = ChatConversation(
            database=actor.database,
            uid=actor.uid,
            title=_title(user_message),
        )
        session.add(conversation)
        session.flush()
        created = True

    session.add_all(
        [
            ChatMessage(
                conversation_id=conversation.id,
                role="user",
                content=user_message,
                internal_workflow=internal_workflow,
            ),
            ChatMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
                internal_workflow=internal_workflow,
            ),
        ]
    )
    conversation.updated_at = datetime.now(UTC)
    session.flush()
    return ChatAppendResponse(conversation_id=conversation.id, created=created)


def recent_chat_text(
    session: Session,
    *,
    actor: ChatActor,
    conversation_id: UUID | None,
    max_messages: int = 8,
    max_chars: int = 5_000,
) -> str:
    if conversation_id is None:
        return ""
    conversation = session.scalar(
        select(ChatConversation.id).where(
            ChatConversation.id == conversation_id,
            ChatConversation.database == actor.database,
            ChatConversation.uid == actor.uid,
        )
    )
    if conversation is None:
        raise ChatStoreError("conversation_not_found")
    newest = tuple(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(max_messages)
        )
    )
    return _bounded_recent_chat_text(newest, max_chars=max_chars)


def _bounded_recent_chat_text(
    newest: tuple[ChatMessage, ...],
    *,
    max_chars: int,
) -> str:
    """Keep the newest bounded slice, then present the retained slice chronologically."""

    retained: list[str] = []
    used = 0
    for item in newest:
        prefix = "User" if item.role == "user" else "Assistant"
        full_line = f"{prefix}: {item.content.strip()}"
        separator = 1 if retained else 0
        remaining = max_chars - used - separator
        if remaining <= 0:
            break
        line = full_line[:remaining]
        retained.append(line)
        used += separator + len(line)
        if len(line) < len(full_line):
            break
    return "\n".join(reversed(retained))


def _conversation_view(value: ChatConversation) -> ChatConversationView:
    return ChatConversationView(
        conversation_id=value.id,
        title=value.title,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _message_view(value: ChatMessage) -> ChatMessageView:
    return ChatMessageView(
        message_id=value.id,
        role=cast(Literal["user", "assistant"], value.role),
        content=value.content,
        created_at=value.created_at,
    )


def _title(message: str) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:79].rstrip() + "…"
