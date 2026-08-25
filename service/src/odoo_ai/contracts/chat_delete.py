"""Contracts for bounded deletion of Assistant chat conversations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from odoo_ai.contracts.chat import ChatActor


class ChatDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: ChatActor
    conversation_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)

    @field_validator("conversation_ids")
    @classmethod
    def validate_unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("conversation ids must be unique")
        return value


class ChatDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deleted_count: int = Field(ge=1, le=50)
