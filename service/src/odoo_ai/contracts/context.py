"""Normalized inputs supplied to a reasoning engine for one turn."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.records import RecordRef
from odoo_ai.contracts.screen_context import ScreenContext


class Workflow(StrEnum):
    """Product workflows understood by the Assistant Service."""

    HOW_TO = "HOW_TO"
    QUERY = "QUERY"
    EXPLAIN = "EXPLAIN"
    DIAGNOSE = "DIAGNOSE"
    ACTION = "ACTION"


class UserRequest(BaseModel):
    """User-authored text for the current turn."""

    model_config = ConfigDict(extra="forbid")

    message: str


class UserExecutionContext(BaseModel):
    """Effective Odoo identity and bounded per-user reasoning preference."""

    model_config = ConfigDict(extra="forbid")

    uid: int
    company_id: int
    allowed_company_ids: list[int] = Field(default_factory=list)
    lang: str | None = None
    reasoning_model: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )


class InstanceProfileSummary(BaseModel):
    """Compact deployment facts relevant to a single turn."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    profile_revision: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class ConversationState(BaseModel):
    """Compact product-owned memory needed for the current turn."""

    model_config = ConfigDict(extra="forbid")

    current_screen: ScreenContext | None = None
    mentioned_records: list[RecordRef] = Field(default_factory=list)
    pending_approval_id: UUID | None = None
    short_summary: str = ""
    last_user_intent: str | None = None


class TurnLimits(BaseModel):
    """Server-enforced budgets exposed as normalized turn data."""

    model_config = ConfigDict(extra="forbid")

    max_tool_calls: int = Field(ge=0)
    max_evidence_items: int = Field(ge=0)


class ContextPack(BaseModel):
    """Compact, typed input passed to a reasoning engine."""

    model_config = ConfigDict(extra="forbid")

    request: UserRequest
    screen: ScreenContext
    user: UserExecutionContext
    workflow_hint: Workflow | None = None
    instance: InstanceProfileSummary
    live_evidence: list[Evidence] = Field(default_factory=list)
    retrieved_evidence: list[Evidence] = Field(default_factory=list)
    conversation_state: ConversationState
    limits: TurnLimits
