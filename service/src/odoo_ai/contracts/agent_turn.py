"""Provider-neutral contracts for the unified host-authorized agent turn."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    field_validator,
    model_validator,
)

from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.context import UserExecutionContext
from odoo_ai.contracts.delegation import OdooGatewayReference
from odoo_ai.contracts.screen_context import ScreenContext

MAX_TOOL_CALLS_PER_TURN = 32
MAX_WRITE_STEPS_PER_PLAN = 12
MAX_REPLANS = 2
MAX_CONSECUTIVE_FAILURES = 3

StepId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
ToolName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")]


class ConfirmationMode(StrEnum):
    """Increasingly permissive confirmation policies."""

    ALWAYS_CONFIRM = "always_confirm"
    RISK_BASED = "risk_based"
    PROTECTED_ONLY = "protected_only"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    PROTECTED = "protected"


class EffectScope(StrEnum):
    READ_ONLY = "read_only"
    INTERNAL_REVERSIBLE = "internal_reversible"
    INTERNAL_IRREVERSIBLE = "internal_irreversible"
    EXTERNAL = "external"


class PlanState(StrEnum):
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AuthorizationSource(StrEnum):
    USER_CONFIRMATION = "user_confirmation"
    EFFECTIVE_POLICY = "effective_policy"


class AgentPolicyLayer(BaseModel):
    """One bounded layer; intersection can only make the effective policy stricter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmation_mode: ConfirmationMode = ConfirmationMode.PROTECTED_ONLY
    max_auto_risk: RiskLevel = RiskLevel.HIGH
    allow_synthetic_data: bool = False
    max_tool_calls_per_turn: int = Field(
        default=MAX_TOOL_CALLS_PER_TURN, strict=True, ge=1, le=MAX_TOOL_CALLS_PER_TURN
    )
    max_write_steps_per_plan: int = Field(
        default=MAX_WRITE_STEPS_PER_PLAN, strict=True, ge=1, le=MAX_WRITE_STEPS_PER_PLAN
    )
    max_replans: int = Field(default=MAX_REPLANS, strict=True, ge=0, le=MAX_REPLANS)
    max_consecutive_failures: int = Field(
        default=MAX_CONSECUTIVE_FAILURES,
        strict=True,
        ge=1,
        le=MAX_CONSECUTIVE_FAILURES,
    )


class AgentPolicyLayers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_ceiling: AgentPolicyLayer
    administrator: AgentPolicyLayer
    user: AgentPolicyLayer
    conversation: AgentPolicyLayer


PolicyLayerName = Literal[
    "system_ceiling", "administrator", "user", "conversation"
]


class EffectiveAgentPolicy(AgentPolicyLayer):
    """Canonical host-computed intersection persisted with a plan."""

    revision: str = Field(min_length=1, max_length=128)
    fingerprint: str = Field(pattern=r"^agent-policy:v1:sha256:[0-9a-f]{64}$")
    constrained_by: tuple[PolicyLayerName, ...] = Field(default=(), max_length=4)


class AgentPolicyView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    confirmation_mode: ConfirmationMode
    max_auto_risk: RiskLevel
    allow_synthetic_data: bool
    constrained_by: tuple[PolicyLayerName, ...] = Field(default=(), max_length=4)


class AgentModelCandidate(BaseModel):
    """Runtime model Odoo has proved visible; it is capability context, not routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$",
    )
    labels: tuple[str, ...] = Field(default=(), max_length=6)

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            not 1 <= len(value) <= 240 or value != value.strip() or "\0" in value
            for value in values
        ):
            raise ValueError("agent model labels must be normalized")
        return values


class AgentCandidateStep(BaseModel):
    """Untrusted LLM proposal. It intentionally carries no authority or risk fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: StepId
    title: str = Field(min_length=1, max_length=240)
    tool_name: ToolName
    arguments: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)
    depends_on: tuple[StepId, ...] = Field(default=(), max_length=MAX_WRITE_STEPS_PER_PLAN)

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        if self.step_id in self.depends_on or len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("agent step dependencies are invalid")
        return self


class AgentCandidateOutput(BaseModel):
    """Only structured output the LLM may return for a unified turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_markdown: str = Field(min_length=1, max_length=16_384)
    confidence: AnswerConfidence
    assumptions: tuple[str, ...] = Field(default=(), max_length=12)
    clarification_question: str | None = Field(default=None, min_length=1, max_length=2_000)
    steps: tuple[AgentCandidateStep, ...] = Field(default=(), max_length=MAX_WRITE_STEPS_PER_PLAN)

    @model_validator(mode="after")
    def validate_plan_shape(self) -> Self:
        ids = tuple(step.step_id for step in self.steps)
        if len(ids) != len(set(ids)):
            raise ValueError("agent step ids must be unique")
        positions = {step_id: position for position, step_id in enumerate(ids)}
        for position, step in enumerate(self.steps):
            if any(dependency not in positions or positions[dependency] >= position for dependency in step.depends_on):
                raise ValueError("agent dependencies must reference earlier steps")
        if self.clarification_question is not None and self.steps:
            raise ValueError("clarification output cannot also propose steps")
        return self


class HostToolPolicySpec(BaseModel):
    """Trusted effect metadata registered by the host, never supplied by Codex."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tool_name: ToolName
    is_write: bool
    needs_schema: bool = False
    is_business_action: bool = False
    effect_scope: EffectScope
    risk_floor: RiskLevel
    atomic: bool
    max_records: int = Field(default=1, strict=True, ge=0, le=MAX_WRITE_STEPS_PER_PLAN)
    allowed_models: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")
    def validate_effect_metadata(self) -> Self:
        if not self.is_write and self.effect_scope is not EffectScope.READ_ONLY:
            raise ValueError("read tool cannot declare a write effect")
        if self.is_write and self.effect_scope is EffectScope.READ_ONLY:
            raise ValueError("write tool must declare an effect")
        if self.effect_scope in {EffectScope.EXTERNAL, EffectScope.INTERNAL_IRREVERSIBLE} and self.risk_floor is not RiskLevel.PROTECTED:
            raise ValueError("protected effects require protected risk")
        return self


class AgentPlanMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    needs_read: bool
    needs_schema: bool
    needs_write: bool
    needs_business_action: bool
    has_external_effect: bool
    has_irreversible_effect: bool
    is_atomic: bool
    estimated_blast_radius: int = Field(strict=True, ge=0, le=MAX_WRITE_STEPS_PER_PLAN)


class AgentPlanStep(BaseModel):
    """Host-normalized step stored after registry and dependency validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: StepId
    title: str = Field(min_length=1, max_length=240)
    tool_name: ToolName
    arguments: dict[str, JsonValue] = Field(default_factory=dict, max_length=32)
    depends_on: tuple[StepId, ...] = Field(default=(), max_length=MAX_WRITE_STEPS_PER_PLAN)
    risk: RiskLevel
    effect_scope: EffectScope
    is_write: bool
    is_business_action: bool
    atomic: bool
    estimated_records: int = Field(strict=True, ge=0, le=MAX_WRITE_STEPS_PER_PLAN)
    payload_fingerprint: str = Field(pattern=r"^agent-step:v1:sha256:[0-9a-f]{64}$")
    proposal_id: UUID | None = None
    proposal_fingerprint: str | None = Field(
        default=None,
        pattern=r"^action-payload:v1:sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_proposal_binding(self) -> Self:
        if (self.proposal_id is None) != (self.proposal_fingerprint is None):
            raise ValueError("agent proposal binding is incomplete")
        return self


class AgentPlanReceiptView(BaseModel):
    """Sanitized verified receipt; no approval authority or executable payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    outcome: str = Field(min_length=1, max_length=64)
    record_model: str | None = Field(
        default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$"
    )
    record_id: int | None = Field(default=None, strict=True, gt=0)
    evidence_id: UUID | None = None
    error_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_record_pointer(self) -> Self:
        if (self.record_model is None) != (self.record_id is None):
            raise ValueError("agent receipt record pointer is incomplete")
        return self


class AgentPlanStepView(BaseModel):
    """Browser-safe state of a normalized plan step."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    step_id: StepId
    title: str = Field(min_length=1, max_length=240)
    state: Literal["planned", "previewed", "executing", "completed", "failed", "skipped"]
    risk: RiskLevel
    effect_scope: EffectScope
    receipt: AgentPlanReceiptView | None = None


class AgentPlanView(BaseModel):
    """Browser-safe view; executable arguments and authority are deliberately absent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    plan_id: UUID
    state: PlanState
    risk: RiskLevel
    metadata: AgentPlanMetadata
    policy: AgentPolicyView
    goal: str = Field(min_length=1, max_length=1_000)
    assumptions: tuple[str, ...] = Field(default=(), max_length=12)
    steps: tuple[AgentPlanStepView, ...] = Field(
        default=(), max_length=MAX_WRITE_STEPS_PER_PLAN
    )
    requires_confirmation: bool
    expires_at: datetime | None = None


class AgentTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: UUID
    actor: ChatActor
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4_000)
    screen: ScreenContext
    user: UserExecutionContext
    gateway: OdooGatewayReference
    capability_token: SecretStr = Field(min_length=1, max_length=8_192)
    candidates: tuple[AgentModelCandidate, ...] = Field(default=(), max_length=32)
    policy_layers: AgentPolicyLayers
    synthetic_data_authorized: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if value != value.strip() or "\0" in value:
            raise ValueError("agent message must be normalized")
        return value

    @model_validator(mode="after")
    def validate_actor(self) -> Self:
        if self.actor.uid != self.user.uid or self.actor.database != self.gateway.database:
            raise ValueError("agent actor must match effective Odoo context")
        models = tuple(candidate.model for candidate in self.candidates)
        if len(models) != len(set(models)):
            raise ValueError("agent candidates must be unique")
        return self


class AgentTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: Literal["ok"] = "ok"
    turn_id: UUID
    conversation_id: UUID | None = None
    state: PlanState
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    confidence: AnswerConfidence
    plan: AgentPlanView | None = None
    completed_at: datetime


class AgentPlanDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: UUID
    decision: Literal["approve", "reject"]
    actor: ChatActor


class AgentPlanExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: UUID
    actor: ChatActor


class AgentPlanDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    plan_id: UUID
    state: Literal[PlanState.AUTHORIZED, PlanState.REJECTED, PlanState.EXPIRED]
    authorization_id: UUID | None = None
    decided_at: datetime

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        if (self.state is PlanState.AUTHORIZED) != (self.authorization_id is not None):
            raise ValueError("agent plan authorization handle is invalid")
        return self


class AgentPlanStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    plan: AgentPlanView
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    error_code: str | None = Field(default=None, max_length=128)
    completed_at: datetime | None = None
