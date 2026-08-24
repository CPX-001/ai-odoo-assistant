"""Contracts for the product-facing persistent chat facade."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.context import UserExecutionContext, Workflow
from odoo_ai.contracts.screen_context import ScreenContext


class ChatActor(BaseModel):
    """Identity derived by Odoo and used only to isolate Assistant chat state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str = Field(min_length=1, max_length=128, pattern=r"^[^\r\n\x00]+$")
    uid: int = Field(gt=0)

    @field_validator("database")
    @classmethod
    def validate_database(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("database must be normalized")
        return value


class ChatHistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: ChatActor
    conversation_id: UUID | None = None
    max_messages: int = Field(default=40, ge=1, le=80)


class ChatConversationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    title: str = Field(min_length=1, max_length=160)
    created_at: datetime
    updated_at: datetime


class ChatMessageView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16_384)
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversations: tuple[ChatConversationView, ...] = Field(default=(), max_length=50)
    active_conversation_id: UUID | None = None
    messages: tuple[ChatMessageView, ...] = Field(default=(), max_length=80)


class ChatAppendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: ChatActor
    conversation_id: UUID | None = None
    user_message: str = Field(min_length=1, max_length=4_000)
    assistant_message: str = Field(min_length=1, max_length=16_384)
    internal_workflow: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z_]+$")

    @field_validator("user_message")
    @classmethod
    def validate_user_message(cls, value: str) -> str:
        if value != value.strip() or "\0" in value:
            raise ValueError("user message must be normalized")
        return value

    @field_validator("assistant_message")
    @classmethod
    def validate_assistant_message(cls, value: str) -> str:
        if not value.strip() or "\0" in value:
            raise ValueError("assistant message must contain safe text")
        return value


class ChatAppendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    created: bool


class GeneralTurnRequest(BaseModel):
    """Read-only turn used when no narrower Odoo workflow is required."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: UUID
    actor: ChatActor
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4_000)
    screen: ScreenContext
    user: UserExecutionContext

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if value != value.strip() or "\0" in value:
            raise ValueError("chat message must be normalized")
        return value

    @model_validator(mode="after")
    def validate_actor(self) -> GeneralTurnRequest:
        if self.actor.uid != self.user.uid:
            raise ValueError("chat actor must match effective user")
        return self


class GeneralTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"
    turn_id: UUID
    workflow: Workflow
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    confidence: AnswerConfidence
    limitations: tuple[str, ...] = Field(default=(), max_length=8)
    evidence_refs: tuple[UUID, ...] = Field(default=(), max_length=24)
    completed_at: datetime
