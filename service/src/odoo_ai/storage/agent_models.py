"""Durable unified-agent plan, step, and audit models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from odoo_ai.storage.base import Base


class AgentPlanRecord(Base):
    __tablename__ = "agent_plan"
    __table_args__ = (
        CheckConstraint("uid > 0 AND company_id > 0", name="ck_agent_plan_actor_positive"),
        CheckConstraint(
            "state IN ('planning','awaiting_confirmation','authorized','executing',"
            "'completed','partial','failed','rejected','expired')",
            name="ck_agent_plan_state",
        ),
        CheckConstraint(
            "risk IN ('low','moderate','high','protected')",
            name="ck_agent_plan_risk",
        ),
        CheckConstraint(
            "plan_fingerprint ~ '^agent-plan:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_fingerprint",
        ),
        CheckConstraint(
            "policy_fingerprint ~ '^agent-policy:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_policy_fingerprint",
        ),
        CheckConstraint("state_version >= 0", name="ck_agent_plan_state_version"),
        Index("ix_agent_plan_actor_created", "database", "uid", "created_at"),
        Index("ix_agent_plan_conversation_created", "conversation_id", "created_at"),
    )

    plan_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    turn_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid)
    database: Mapped[str] = mapped_column(String(128), nullable=False)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_company_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    goal: Mapped[str] = mapped_column(String(1_000), nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    metadata_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    policy_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_plan: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authorization_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    authorization_source: Mapped[str | None] = mapped_column(String(32))
    decided_by_uid: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentPlanStepRecord(Base):
    __tablename__ = "agent_plan_step"
    __table_args__ = (
        CheckConstraint("position >= 0 AND position < 12", name="ck_agent_plan_step_position"),
        CheckConstraint(
            "state IN ('planned','previewed','executing','completed','failed','skipped')",
            name="ck_agent_plan_step_state",
        ),
        CheckConstraint(
            "risk IN ('low','moderate','high','protected')",
            name="ck_agent_plan_step_risk",
        ),
        CheckConstraint(
            "effect_scope IN ('read_only','internal_reversible','internal_irreversible','external')",
            name="ck_agent_plan_step_effect_scope",
        ),
        CheckConstraint(
            "payload_fingerprint ~ '^agent-step:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_step_fingerprint",
        ),
        UniqueConstraint("plan_id", "position", name="uq_agent_plan_step_position"),
        UniqueConstraint("plan_id", "step_id", name="uq_agent_plan_step_id"),
        Index("ix_agent_plan_step_plan_state", "plan_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_plan.plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    effect_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    is_write: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_business_action: Mapped[bool] = mapped_column(Boolean, nullable=False)
    atomic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    estimated_records: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_id: Mapped[UUID | None] = mapped_column(Uuid)
    proposal_fingerprint: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    receipt: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentPlanAuditRecord(Base):
    __tablename__ = "agent_plan_audit_event"
    __table_args__ = (
        CheckConstraint("actor_uid > 0", name="ck_agent_plan_audit_actor_positive"),
        Index("ix_agent_plan_audit_plan_created", "plan_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plan_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("agent_plan.plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
