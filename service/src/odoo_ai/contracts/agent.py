"""Descriptions and structured output for an agent turn."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from odoo_ai.contracts.context import Workflow


class ToolRisk(StrEnum):
    """Operation categories declared by tools, not execution authority."""

    READ = "read"
    METADATA = "metadata"
    WRITE_PREVIEW = "write-preview"
    WRITE = "write"
    ACTION_PREVIEW = "action-preview"
    ACTION = "action"


class ToolSpec(BaseModel):
    """Serializable description of a bounded tool available to an engine."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, JsonValue]
    risk: ToolRisk
    executor_id: str


class AnswerConfidence(StrEnum):
    """Confidence levels rendered with the final answer."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProposedAction(BaseModel):
    """Presentation-only summary of a proposal; it grants no write authority."""

    model_config = ConfigDict(extra="forbid")

    action_type: str
    summary: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class AnswerEnvelope(BaseModel):
    """Validated, citable output returned by a reasoning engine."""

    model_config = ConfigDict(extra="forbid")

    answer_markdown: str
    workflow: Workflow
    confidence: AnswerConfidence
    evidence_refs: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    proposed_action: ProposedAction | None = None
