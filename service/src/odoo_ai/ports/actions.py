"""Persistence boundary for durable ACTION proposals and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from odoo_ai.contracts import (
    ActionActorContext,
    ActionAuthorityClaims,
    ActionDecision,
    ActionPreview,
    ActionProposalPayload,
    ActionProposalState,
)


class ActionAuthorityIssuer(Protocol):
    def encode(self, claims: ActionAuthorityClaims) -> str: ...


@dataclass(frozen=True, slots=True)
class StoredActionProposal:
    """Validated application view of one immutable proposal plus mutable state."""

    payload: ActionProposalPayload
    canonical_payload: str
    payload_fingerprint: str
    preview: ActionPreview
    state: ActionProposalState
    created_at: datetime
    decided_at: datetime | None = None
    decided_by_uid: int | None = None
    approval_id: UUID | None = None
    state_version: int = 0
    attempt_id: UUID | None = None
    execution_started_at: datetime | None = None
    completed_at: datetime | None = None
    evidence_id: UUID | None = None
    error_code: str | None = None
    verification_payload: dict[str, object] | None = None


class ActionDecisionOutcome(StrEnum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    BINDING_MISMATCH = "binding_mismatch"
    EXPIRED = "expired"
    INVALID_STATE = "invalid_state"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class StoredDecisionResult:
    outcome: ActionDecisionOutcome
    proposal: StoredActionProposal | None = None


class ActionApprovalStore(Protocol):
    """Atomic storage operations; implementations own transaction boundaries."""

    def create_preview(self, proposal: StoredActionProposal) -> None: ...

    def get_by_proposal_id(self, proposal_id: UUID) -> StoredActionProposal | None: ...

    def get_by_approval_id(self, approval_id: UUID) -> StoredActionProposal | None: ...

    def decide(
        self,
        *,
        proposal_id: UUID,
        decision: ActionDecision,
        actor: ActionActorContext,
        decided_at: datetime,
        approval_id: UUID | None,
    ) -> StoredDecisionResult: ...

    def claim_execution(
        self,
        *,
        approval_id: UUID,
        actor: ActionActorContext,
        attempt_id: UUID,
        started_at: datetime,
    ) -> StoredDecisionResult: ...

    def transition_execution(
        self,
        *,
        proposal_id: UUID,
        attempt_id: UUID,
        expected_states: tuple[ActionProposalState, ...],
        state: ActionProposalState,
        occurred_at: datetime,
        evidence_id: UUID | None = None,
        error_code: str | None = None,
        verification_payload: dict[str, object] | None = None,
    ) -> StoredActionProposal: ...
