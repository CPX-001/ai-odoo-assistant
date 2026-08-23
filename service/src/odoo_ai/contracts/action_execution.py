"""Closed contracts for one approved ACTION commit and verification."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from odoo_ai.contracts.action import ActionValue, Fingerprint
from odoo_ai.contracts.action_approval import ActionActorContext, ActionProposalState
from odoo_ai.contracts.evidence import Evidence


class ExecuteApprovedActionRequest(BaseModel):
    """Minimal authenticated execution input; values are loaded from storage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approval_id: UUID
    actor: ActionActorContext


class ActionAuthorityClaims(BaseModel):
    """Exact a1 authority independently scoped from read/query/preview tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[1] = 1
    jti: str = Field(pattern=r"^[A-Za-z0-9_-]{22,64}$")
    proposal_id: UUID
    approval_id: UUID
    attempt_id: UUID
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: int = Field(strict=True, gt=0)
    company_id: int = Field(strict=True, gt=0)
    allowed_company_ids: tuple[int, ...] = Field(min_length=1, max_length=16)
    model: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
    record_id: int = Field(strict=True, gt=0)
    fields: tuple[str, ...] = Field(min_length=1, max_length=4)
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    policy_revision: str = Field(min_length=1, max_length=128)
    schema_revision: str = Field(min_length=1, max_length=128)
    scopes: tuple[Literal["action_commit", "action_verify"], ...]
    issued_at: int = Field(strict=True, ge=0)
    expires_at: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_closed_authority(self) -> ActionAuthorityClaims:
        if (
            self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
            or self.fields != tuple(sorted(set(self.fields)))
            or any(not field or not field.replace("_", "a").isalnum() for field in self.fields)
            or len(self.scopes) != 1
        ):
            raise ValueError("invalid action authority")
        return self


class ActionCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    attempt_id: UUID
    committed_at: AwareDatetime
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint


class ActionVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    attempt_id: UUID
    verified_at: AwareDatetime
    matches: bool
    after: dict[str, ActionValue]


class ActionExecutionReceipt(BaseModel):
    """Sanitized durable outcome; never includes authority or secret material."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    approval_id: UUID
    attempt_id: UUID
    state: Literal[
        ActionProposalState.VERIFIED,
        ActionProposalState.STALE,
        ActionProposalState.FAILED,
        ActionProposalState.EXECUTION_UNKNOWN,
        ActionProposalState.COMMITTED_UNVERIFIED,
    ]
    payload_fingerprint: Fingerprint
    completed_at: AwareDatetime
    evidence_id: UUID | None = None
    evidence: Evidence | None = None
    error_code: str | None = Field(default=None, max_length=128)
