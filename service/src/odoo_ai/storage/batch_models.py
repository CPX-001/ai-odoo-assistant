"""SQLAlchemy models for durable execution-ready batch mutation jobs."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from odoo_ai.storage.base import Base


class BatchMutationJobRecord(Base):
    __tablename__ = "batch_mutation_job"
    __table_args__ = (
        CheckConstraint("uid > 0 AND company_id > 0", name="ck_batch_job_actor_positive"),
        CheckConstraint(
            "operation IN ('create','patch','delete')",
            name="ck_batch_job_operation",
        ),
        CheckConstraint(
            "failure_mode IN ('continue_on_error','atomic_chunk')",
            name="ck_batch_job_failure_mode",
        ),
        CheckConstraint(
            "((operation IN ('create','patch')) AND schema_id IS NOT NULL) OR "
            "(operation = 'delete' AND schema_id IS NULL)",
            name="ck_batch_job_schema_shape",
        ),
        CheckConstraint(
            "state IN ('prepared','executing','execution_unknown','completed','partial','failed')",
            name="ck_batch_job_state",
        ),
        CheckConstraint(
            "job_fingerprint ~ '^batch-job:v1:sha256:[0-9a-f]{64}$'",
            name="ck_batch_job_fingerprint",
        ),
        CheckConstraint(
            "item_count BETWEEN 1 AND 500 AND applied_count >= 0 AND failed_count >= 0 "
            "AND applied_count + failed_count <= item_count",
            name="ck_batch_job_counts",
        ),
        CheckConstraint(
            "(state = 'prepared' AND attempt_id IS NULL AND execution_started_at IS NULL "
            "AND completed_at IS NULL AND applied_count = 0 AND failed_count = 0) OR "
            "(state IN ('executing','execution_unknown') AND attempt_id IS NOT NULL "
            "AND execution_started_at IS NOT NULL AND completed_at IS NULL "
            "AND applied_count = 0 AND failed_count = 0) OR "
            "(state = 'completed' AND attempt_id IS NOT NULL AND execution_started_at IS NOT NULL "
            "AND completed_at IS NOT NULL AND applied_count = item_count AND failed_count = 0) OR "
            "(state = 'partial' AND attempt_id IS NOT NULL AND execution_started_at IS NOT NULL "
            "AND completed_at IS NOT NULL AND applied_count > 0 AND failed_count > 0 "
            "AND applied_count + failed_count = item_count) OR "
            "(state = 'failed' AND attempt_id IS NOT NULL AND execution_started_at IS NOT NULL "
            "AND completed_at IS NOT NULL AND applied_count = 0 AND failed_count = item_count)",
            name="ck_batch_job_state_shape",
        ),
        CheckConstraint("state_version >= 0", name="ck_batch_job_state_version"),
        Index("ix_batch_job_actor_created", "database", "uid", "created_at"),
        Index("ix_batch_job_source", "source_provider", "source_reference"),
        Index("ix_batch_job_conversation_created", "conversation_id", "created_at"),
    )

    job_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    turn_id: Mapped[UUID | None] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid)
    instance_id: Mapped[str] = mapped_column(String(255), nullable=False)
    database: Mapped[str] = mapped_column(String(128), nullable=False)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_company_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_id: Mapped[str | None] = mapped_column(String(128))
    failure_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(128))
    spec_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    job_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="prepared")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BatchMutationItemRecord(Base):
    __tablename__ = "batch_mutation_item"
    __table_args__ = (
        CheckConstraint("position >= 0 AND position < 500", name="ck_batch_item_position"),
        CheckConstraint(
            "item_fingerprint ~ '^batch-item:v1:sha256:[0-9a-f]{64}$'",
            name="ck_batch_item_fingerprint",
        ),
        CheckConstraint(
            "state IN ('pending','applied','failed')",
            name="ck_batch_item_state",
        ),
        CheckConstraint(
            "(state = 'pending' AND result_payload IS NULL) OR "
            "(state IN ('applied','failed') AND result_payload IS NOT NULL)",
            name="ck_batch_item_result_shape",
        ),
        UniqueConstraint("job_id", "position", name="uq_batch_item_position"),
        UniqueConstraint("job_id", "source_ref", name="uq_batch_item_source_ref"),
        Index("ix_batch_item_job_state", "job_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("batch_mutation_job.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    item_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    item_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    result_payload: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BatchMutationAuditRecord(Base):
    __tablename__ = "batch_mutation_audit_event"
    __table_args__ = (
        CheckConstraint("actor_uid > 0", name="ck_batch_audit_actor_positive"),
        Index("ix_batch_audit_job_created", "job_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("batch_mutation_job.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[UUID | None] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    job_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
