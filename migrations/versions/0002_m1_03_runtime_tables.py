"""Add minimal instance, capability, and trace persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_m1_03_runtime_tables"
down_revision: str | None = "0001_m1_02_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_profile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instance_id"),
    )
    op.create_table(
        "capability_snapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_profile_id", sa.Uuid(), nullable=False),
        sa.Column("readiness", sa.String(length=32), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "readiness IN ('FULLY_READY', 'DEGRADED', 'ERROR')",
            name="ck_capability_snapshot_readiness",
        ),
        sa.ForeignKeyConstraint(
            ["instance_profile_id"], ["instance_profile.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_capability_snapshot_instance_created",
        "capability_snapshot",
        ["instance_profile_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "trace_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(event_name) > 0", name="ck_trace_event_name_nonempty"),
        sa.CheckConstraint("sequence >= 0", name="ck_trace_event_sequence_nonnegative"),
        sa.CheckConstraint("char_length(status) > 0", name="ck_trace_event_status_nonempty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id", "sequence", name="uq_trace_event_trace_sequence"),
    )


def downgrade() -> None:
    op.drop_table("trace_event")
    op.drop_index("ix_capability_snapshot_instance_created", table_name="capability_snapshot")
    op.drop_table("capability_snapshot")
    op.drop_table("instance_profile")
