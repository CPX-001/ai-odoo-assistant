"""Strict durable-approval contracts for the M6 ACTION boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.action import (
    MAX_ACTION_COMPANIES,
    ActionPreview,
    ActionProposalPayload,
    Fingerprint,
)

PositiveId = Annotated[int, Field(strict=True, gt=0)]


class ActionProposalState(StrEnum):
    """Closed state machine shared by approval, execution and verification."""

    PREVIEWED = "previewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    COMMITTED = "committed"
    VERIFIED = "verified"
    STALE = "stale"
    FAILED = "failed"
    EXECUTION_UNKNOWN = "execution_unknown"
    COMMITTED_UNVERIFIED = "committed_unverified"


class ActionDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ActionActorContext(BaseModel):
    """Identity and companies derived by authenticated Odoo server code."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: PositiveId
    company_id: PositiveId
    allowed_company_ids: tuple[PositiveId, ...] = Field(
        min_length=1, max_length=MAX_ACTION_COMPANIES
    )

    @field_validator("database", "instance_id")
    @classmethod
    def validate_binding_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("actor binding is invalid")
        return value

    @model_validator(mode="after")
    def validate_companies(self) -> Self:
        if self.company_id not in self.allowed_company_ids:
            raise ValueError("effective company must be allowed")
        if self.allowed_company_ids != tuple(sorted(self.allowed_company_ids)):
            raise ValueError("allowed companies must be canonically ordered")
        if len(self.allowed_company_ids) != len(set(self.allowed_company_ids)):
            raise ValueError("allowed companies must be unique")
        return self


class PersistActionPreviewRequest(BaseModel):
    """Host-produced proposal and exact checked preview to persist."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    payload: ActionProposalPayload
    preview: ActionPreview


class PersistActionPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    state: Literal[ActionProposalState.PREVIEWED] = ActionProposalState.PREVIEWED
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    expires_at: AwareDatetime


class ActionDecisionRequest(BaseModel):
    """Minimal authenticated decision; replacement payload data is forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    decision: ActionDecision
    actor: ActionActorContext


class ActionDecisionReceipt(BaseModel):
    """Opaque handle and immutable decision facts returned to Odoo."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    approval_id: UUID | None = None
    state: Literal[ActionProposalState.APPROVED, ActionProposalState.REJECTED]
    payload_fingerprint: Fingerprint
    decided_by_uid: PositiveId
    decided_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_handle(self) -> Self:
        if (self.state is ActionProposalState.APPROVED) != (self.approval_id is not None):
            raise ValueError("approval handle does not match decision")
        return self
