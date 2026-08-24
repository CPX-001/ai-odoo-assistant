"""Authenticated ACTION turn and deterministic decision transport contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from odoo_ai.contracts.action import (
    MAX_ACTION_FIELDS,
    MAX_ACTION_WARNINGS,
    SALE_ORDER_CONFIRM_ACTION_ID,
    ActionCreatePreviewValue,
    ActionCreateTarget,
    ActionKind,
    ActionPreviewChange,
    ActionTarget,
    BusinessActionId,
    Fingerprint,
)
from odoo_ai.contracts.action_approval import ActionDecision, ActionProposalState
from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.context import Workflow
from odoo_ai.contracts.delegation import ContextReadTurnRequest
from odoo_ai.contracts.tool_execution import ToolExecutionReport


class ActionTurnRequest(ContextReadTurnRequest):
    """Odoo ingress carrying the separately signed, preview-only p1 token."""


class ActionProposalHandle(BaseModel):
    """Browser-safe handle for the exact durable preview produced in this turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    turn_id: UUID
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    target: ActionTarget
    changes: tuple[ActionPreviewChange, ...] = Field(
        min_length=1, max_length=MAX_ACTION_FIELDS
    )
    warnings: tuple[Annotated[str, Field(min_length=1, max_length=512)], ...] = Field(
        default=(), max_length=MAX_ACTION_WARNINGS
    )
    expires_at: datetime
    evidence_id: UUID


class ActionCreateProposalHandle(BaseModel):
    """Browser-safe presentation of a persisted effect-free create preview."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_kind: Literal[ActionKind.RECORD_CREATE] = ActionKind.RECORD_CREATE
    proposal_id: UUID
    turn_id: UUID
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    target: ActionCreateTarget
    values: tuple[ActionCreatePreviewValue, ...] = Field(
        min_length=1, max_length=MAX_ACTION_FIELDS
    )
    warnings: tuple[Annotated[str, Field(min_length=1, max_length=512)], ...] = Field(
        default=(), max_length=MAX_ACTION_WARNINGS
    )
    expires_at: datetime
    evidence_id: UUID


class BusinessActionProposalHandle(BaseModel):
    """Browser-safe presentation of an exact curated business action preview."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_kind: Literal[ActionKind.BUSINESS_ACTION] = ActionKind.BUSINESS_ACTION
    action_id: BusinessActionId = SALE_ORDER_CONFIRM_ACTION_ID
    proposal_id: UUID
    turn_id: UUID
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    target: ActionTarget | ActionCreateTarget
    display_name: str = Field(min_length=1, max_length=256)
    state_before: str | None = Field(default=None, max_length=64)
    expected_states: tuple[str, ...] = Field(min_length=1, max_length=8)
    details: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=16)
    warnings: tuple[Annotated[str, Field(min_length=1, max_length=512)], ...] = Field(
        default=(), max_length=MAX_ACTION_WARNINGS
    )
    expires_at: datetime
    evidence_id: UUID


ActionProposalPresentation = (
    ActionProposalHandle | ActionCreateProposalHandle | BusinessActionProposalHandle
)


class ActionProposalTrace(BaseModel):
    """Host-only binding between an executed preview call and its durable proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, JsonValue] = Field(max_length=32)
    proposal_id: UUID
    payload_fingerprint: Fingerprint


class ActionTurnResponse(BaseModel):
    """Sanitized ACTION presentation returned to Odoo; it grants no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    turn_id: UUID
    status: Literal["ok"] = "ok"
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    workflow: Literal[Workflow.ACTION] = Workflow.ACTION
    confidence: AnswerConfidence
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=1_024)], ...] = Field(
        default=(), max_length=8
    )
    evidence_refs: tuple[UUID, ...] = Field(default=(), max_length=8)
    proposal: ActionProposalPresentation | None = None
    completed_at: datetime


class ActionToolReport(BaseModel):
    """Host-only report proving which proposal was produced by this exact turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_report: ToolExecutionReport = Field(default_factory=ToolExecutionReport)
    proposals: tuple[ActionProposalPresentation, ...] = Field(default=(), max_length=12)
    proposal_traces: tuple[ActionProposalTrace, ...] = Field(default=(), max_length=12)


class OdooActionActorContext(BaseModel):
    """Identity facts derived by Odoo; instance binding is loaded from the proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    database: str = Field(min_length=1, max_length=128)
    uid: int = Field(strict=True, gt=0)
    company_id: int = Field(strict=True, gt=0)
    allowed_company_ids: tuple[int, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if (
            self.database != self.database.strip()
            or any(ord(character) < 32 for character in self.database)
            or self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
        ):
            raise ValueError("invalid Odoo ACTION actor")
        return self


class ActionDecisionCommandRequest(BaseModel):
    """Minimal host-controlled decision; replacement target/values are impossible."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    decision: ActionDecision
    actor: OdooActionActorContext


class ActionCommandReceipt(BaseModel):
    """Unified sanitized reject or post-verification execution outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    state: Literal[
        ActionProposalState.REJECTED,
        ActionProposalState.VERIFIED,
        ActionProposalState.STALE,
        ActionProposalState.FAILED,
        ActionProposalState.EXECUTION_UNKNOWN,
        ActionProposalState.COMMITTED_UNVERIFIED,
    ]
    payload_fingerprint: Fingerprint
    completed_at: datetime
    approval_id: UUID | None = None
    attempt_id: UUID | None = None
    evidence_id: UUID | None = None
    record_model: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$"
    )
    record_id: int | None = Field(default=None, strict=True, gt=0)
    error_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        rejected = self.state is ActionProposalState.REJECTED
        if rejected and (self.approval_id is not None or self.attempt_id is not None):
            raise ValueError("rejected ACTION cannot carry execution handles")
        if not rejected and (self.approval_id is None or self.attempt_id is None):
            raise ValueError("execution outcome requires opaque handles")
        if (self.state is ActionProposalState.VERIFIED) != (self.evidence_id is not None):
            raise ValueError("verified ACTION requires checked evidence")
        if (self.record_model is None) != (self.record_id is None):
            raise ValueError("ACTION record pointer is incomplete")
        if self.state is not ActionProposalState.VERIFIED and self.record_id is not None:
            raise ValueError("only verified ACTION can expose a record pointer")
        return self
