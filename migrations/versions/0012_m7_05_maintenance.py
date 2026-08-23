"""Persist bounded M7 maintenance jobs and audit events.

Revision ID: 0012_m7_05_maintenance
Revises: 0011_m7_03_runtime_configuration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_m7_05_maintenance"
down_revision: str | None = "0011_m7_03_runtime_configuration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_OPERATIONS = "'source_rescan','knowledge_reindex'"
_ALL_OPERATIONS = (
    "'readiness_test','source_rescan','source_test','logs_test',"
    "'knowledge_reindex','reasoning_test','action_self_test','configuration_revalidate'"
)
_STATES = "'queued','running','succeeded','failed'"


def upgrade() -> None:
    op.create_table(
        "maintenance_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("actor_database", sa.String(length=128), nullable=False),
        sa.Column("result_code", sa.String(length=128), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"operation IN ({_JOB_OPERATIONS})",
            name="ck_maintenance_job_operation",
        ),
        sa.CheckConstraint(f"state IN ({_STATES})", name="ck_maintenance_job_state"),
        sa.CheckConstraint("actor_uid > 0", name="ck_maintenance_job_actor_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(metrics) = 'object'",
            name="ck_maintenance_job_metrics_object",
        ),
        sa.CheckConstraint(
            "(state = 'queued' AND started_at IS NULL AND completed_at IS NULL AND result_code IS NULL) OR "
            "(state = 'running' AND started_at IS NOT NULL AND completed_at IS NULL AND result_code IS NULL) OR "
            "(state IN ('succeeded','failed') AND started_at IS NOT NULL AND completed_at IS NOT NULL AND result_code IS NOT NULL)",
            name="ck_maintenance_job_state_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_maintenance_job_active_operation",
        "maintenance_job",
        ["operation"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued','running')"),
    )
    op.create_index(
        "ix_maintenance_job_created",
        "maintenance_job",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "maintenance_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("actor_database", sa.String(length=128), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_code", sa.String(length=128), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            f"operation IN ({_ALL_OPERATIONS})",
            name="ck_maintenance_audit_operation",
        ),
        sa.CheckConstraint(f"state IN ({_STATES})", name="ck_maintenance_audit_state"),
        sa.CheckConstraint("actor_uid > 0", name="ck_maintenance_audit_actor_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(metrics) = 'object'",
            name="ck_maintenance_audit_metrics_object",
        ),
        sa.CheckConstraint(
            "(state IN ('queued','running') AND result_code IS NULL) OR "
            "(state IN ('succeeded','failed') AND result_code IS NOT NULL)",
            name="ck_maintenance_audit_result_shape",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["maintenance_job.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_audit_operation_created",
        "maintenance_audit_event",
        ["operation", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_audit_operation_created",
        table_name="maintenance_audit_event",
    )
    op.drop_table("maintenance_audit_event")
    op.drop_index("ix_maintenance_job_created", table_name="maintenance_job")
    op.drop_index(
        "uq_maintenance_job_active_operation",
        table_name="maintenance_job",
    )
    op.drop_table("maintenance_job")
