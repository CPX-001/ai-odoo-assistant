"""Persist immutable execution-ready batch mutation jobs.

Revision ID: 0015_batch_mutation_jobs
Revises: 0014_agent_plans
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_batch_mutation_jobs"
down_revision: str | None = "0014_agent_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "batch_mutation_job",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("instance_id", sa.String(length=255), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("allowed_company_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("target_model", sa.String(length=128), nullable=False),
        sa.Column("schema_id", sa.String(length=128), nullable=True),
        sa.Column("failure_mode", sa.String(length=32), nullable=False),
        sa.Column("policy_revision", sa.String(length=128), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("spec_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("job_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="prepared"),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("uid > 0 AND company_id > 0", name="ck_batch_job_actor_positive"),
        sa.CheckConstraint(
            "operation IN ('create','patch','delete')",
            name="ck_batch_job_operation",
        ),
        sa.CheckConstraint(
            "failure_mode IN ('continue_on_error','atomic_chunk')",
            name="ck_batch_job_failure_mode",
        ),
        sa.CheckConstraint(
            "((operation IN ('create','patch')) AND schema_id IS NOT NULL) OR "
            "(operation = 'delete' AND schema_id IS NULL)",
            name="ck_batch_job_schema_shape",
        ),
        sa.CheckConstraint(
            "state IN ('prepared','executing','execution_unknown','completed','partial','failed')",
            name="ck_batch_job_state",
        ),
        sa.CheckConstraint(
            "job_fingerprint ~ '^batch-job:v1:sha256:[0-9a-f]{64}$'",
            name="ck_batch_job_fingerprint",
        ),
        sa.CheckConstraint(
            "item_count BETWEEN 1 AND 500 AND applied_count >= 0 AND failed_count >= 0 "
            "AND applied_count + failed_count <= item_count",
            name="ck_batch_job_counts",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint("state_version >= 0", name="ck_batch_job_state_version"),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("job_fingerprint"),
        sa.UniqueConstraint("attempt_id"),
    )
    op.create_index(
        "ix_batch_job_actor_created",
        "batch_mutation_job",
        ["database", "uid", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_batch_job_source",
        "batch_mutation_job",
        ["source_provider", "source_reference"],
        unique=False,
    )
    op.create_index(
        "ix_batch_job_conversation_created",
        "batch_mutation_job",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "batch_mutation_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("item_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("item_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0 AND position < 500", name="ck_batch_item_position"),
        sa.CheckConstraint(
            "item_fingerprint ~ '^batch-item:v1:sha256:[0-9a-f]{64}$'",
            name="ck_batch_item_fingerprint",
        ),
        sa.CheckConstraint(
            "state IN ('pending','applied','failed')",
            name="ck_batch_item_state",
        ),
        sa.CheckConstraint(
            "(state = 'pending' AND result_payload IS NULL) OR "
            "(state IN ('applied','failed') AND result_payload IS NOT NULL)",
            name="ck_batch_item_result_shape",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["batch_mutation_job.job_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "position", name="uq_batch_item_position"),
        sa.UniqueConstraint("job_id", "source_ref", name="uq_batch_item_source_ref"),
    )
    op.create_index(
        "ix_batch_item_job_state",
        "batch_mutation_item",
        ["job_id", "state"],
        unique=False,
    )

    op.create_table(
        "batch_mutation_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("job_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("actor_uid > 0", name="ck_batch_audit_actor_positive"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["batch_mutation_job.job_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_batch_audit_job_created",
        "batch_mutation_audit_event",
        ["job_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_batch_audit_job_created", table_name="batch_mutation_audit_event")
    op.drop_table("batch_mutation_audit_event")
    op.drop_index("ix_batch_item_job_state", table_name="batch_mutation_item")
    op.drop_table("batch_mutation_item")
    op.drop_index("ix_batch_job_conversation_created", table_name="batch_mutation_job")
    op.drop_index("ix_batch_job_source", table_name="batch_mutation_job")
    op.drop_index("ix_batch_job_actor_created", table_name="batch_mutation_job")
    op.drop_table("batch_mutation_job")
