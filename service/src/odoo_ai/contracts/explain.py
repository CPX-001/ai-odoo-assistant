"""Narrow contracts for the M4 contextual EXPLAIN workflow."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.context import Workflow
from odoo_ai.contracts.delegation import ContextReadTurnRequest


class ExplainTurnRequest(ContextReadTurnRequest):
    """Authenticated Odoo-server ingress reusing the M2 authority contract."""


class RecordCitation(BaseModel):
    """Browser-safe pointer to the current Odoo record evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["record"] = "record"
    evidence_id: UUID
    model: str = Field(min_length=1, max_length=128)
    id: int = Field(strict=True, gt=0)
    display_name: str | None = Field(default=None, max_length=512)
    captured_at: datetime


class SourceCitation(BaseModel):
    """Browser-safe logical pointer to fingerprint-checked source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["source"] = "source"
    evidence_id: UUID
    module: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_]+$")
    logical_path: str = Field(min_length=1, max_length=1024)
    start_line: int = Field(strict=True, gt=0)
    end_line: int = Field(strict=True, gt=0)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provenance: str = Field(min_length=1, max_length=64)


ExplainCitation = Annotated[
    RecordCitation | SourceCitation,
    Field(discriminator="kind"),
]


class ExplainTurnResponse(BaseModel):
    """Sanitized result returned to Odoo without raw evidence or tool transcripts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: UUID
    status: Literal["ok"] = "ok"
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    workflow: Literal[Workflow.EXPLAIN] = Workflow.EXPLAIN
    confidence: AnswerConfidence
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=1_024)], ...] = Field(
        default=(), max_length=8
    )
    citations: tuple[ExplainCitation, ...] = Field(default=(), max_length=24)
    completed_at: datetime
