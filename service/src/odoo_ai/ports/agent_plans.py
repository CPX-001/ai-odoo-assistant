"""Ports and immutable snapshots for grouped agent plan state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from odoo_ai.contracts import (
    AgentPlanMetadata,
    AgentPlanStep,
    AuthorizationSource,
    EffectiveAgentPolicy,
    PlanState,
    RiskLevel,
)
from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.chat import ChatActor


@dataclass(frozen=True, slots=True)
class StoredAgentPlan:
    plan_id: UUID
    turn_id: UUID
    conversation_id: UUID | None
    actor: ChatActor
    company_id: int
    allowed_company_ids: tuple[int, ...]
    goal: str
    answer_markdown: str
    confidence: AnswerConfidence
    assumptions: tuple[str, ...]
    state: PlanState
    risk: RiskLevel
    metadata: AgentPlanMetadata
    policy: EffectiveAgentPolicy
    steps: tuple[AgentPlanStep, ...]
    canonical_plan: dict[str, object]
    plan_fingerprint: str
    requires_confirmation: bool
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    authorization_id: UUID | None = None
    authorization_source: AuthorizationSource | None = None
    decided_by_uid: int | None = None
    decided_at: datetime | None = None
    execution_started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    state_version: int = 0
    step_results: tuple[StoredAgentPlanStepResult, ...] = ()


@dataclass(frozen=True, slots=True)
class StoredAgentPlanStepResult:
    step_id: str
    state: Literal["planned", "previewed", "executing", "completed", "failed", "skipped"]
    receipt: dict[str, object] | None
    error_code: str | None
    updated_at: datetime


class AgentPlanTransitionOutcome(StrEnum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    BINDING_MISMATCH = "binding_mismatch"
    INVALID_STATE = "invalid_state"
    EXPIRED = "expired"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class AgentPlanTransitionResult:
    outcome: AgentPlanTransitionOutcome
    plan: StoredAgentPlan | None = None


class AgentPlanStore(Protocol):
    def create(self, plan: StoredAgentPlan) -> None: ...

    def get(self, plan_id: UUID) -> StoredAgentPlan | None: ...

    def decide(
        self,
        *,
        plan_id: UUID,
        actor: ChatActor,
        approve: bool,
        authorization_id: UUID | None,
        decided_at: datetime,
    ) -> AgentPlanTransitionResult: ...

    def claim_execution(
        self,
        *,
        plan_id: UUID,
        actor: ChatActor,
        started_at: datetime,
    ) -> AgentPlanTransitionResult: ...

    def complete(
        self,
        *,
        plan_id: UUID,
        state: PlanState,
        completed_at: datetime,
        error_code: str | None = None,
    ) -> StoredAgentPlan: ...

    def record_step_result(
        self,
        *,
        plan_id: UUID,
        step_id: str,
        state: Literal["completed", "failed", "skipped"],
        occurred_at: datetime,
        receipt: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> None: ...
