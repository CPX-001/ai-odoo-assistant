"""Authenticated transport and browser-safe output for the QUERY workflow."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.context import Workflow
from odoo_ai.contracts.delegation import ContextReadTurnRequest


class QueryTurnRequest(ContextReadTurnRequest):
    """Odoo-server ingress carrying the separate q1 QUERY authority."""

    delegation_token: SecretStr = Field(min_length=1, max_length=8192)


class QueryCitation(BaseModel):
    """Browser-safe pointer to one checked bounded ORM result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["query"] = "query"
    evidence_id: UUID
    model: str = Field(min_length=1, max_length=128)
    operation: Literal["query_records", "aggregate_records"]
    captured_at: datetime
    returned_count: int = Field(strict=True, ge=0, le=50)
    limit: int = Field(strict=True, ge=1, le=50)
    truncated: bool
    empty: bool


class QueryTurnResponse(BaseModel):
    """Sanitized QUERY answer returned to Odoo without rows or tool transcripts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: UUID
    status: Literal["ok"] = "ok"
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    workflow: Literal[Workflow.QUERY] = Workflow.QUERY
    confidence: AnswerConfidence
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=1_024)], ...] = Field(
        default=(), max_length=8
    )
    citations: tuple[QueryCitation, ...] = Field(default=(), max_length=8)
    completed_at: datetime
