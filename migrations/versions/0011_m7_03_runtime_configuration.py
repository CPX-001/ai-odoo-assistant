"""Persist revision-guarded M7 runtime configuration.

Revision ID: 0011_m7_03_runtime_configuration
Revises: 0010_m6_12_business_action
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_m7_03_runtime_configuration"
down_revision: str | None = "0010_m6_12_business_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_config_revision",
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("revision > 0", name="ck_runtime_config_revision_positive"),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_runtime_config_revision_fingerprint",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(overrides) = 'object'",
            name="ck_runtime_config_revision_overrides_object",
        ),
        sa.PrimaryKeyConstraint("revision"),
    )
    op.create_table(
        "runtime_config_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("current_fingerprint", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_runtime_config_state_singleton"),
        sa.CheckConstraint(
            "current_revision >= 0", name="ck_runtime_config_state_revision_nonnegative"
        ),
        sa.CheckConstraint(
            "(current_revision = 0 AND current_fingerprint IS NULL) OR "
            "(current_revision > 0 AND current_fingerprint ~ '^[0-9a-f]{64}$')",
            name="ck_runtime_config_state_fingerprint_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "runtime_config_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("actor_database", sa.String(length=128), nullable=False),
        sa.Column("changed_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("actor_uid > 0", name="ck_runtime_config_audit_actor_positive"),
        sa.CheckConstraint(
            "event_type = 'configuration_applied'",
            name="ck_runtime_config_audit_event_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(changed_keys) = 'array'",
            name="ck_runtime_config_audit_changed_keys_array",
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_runtime_config_audit_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["revision"],
            ["runtime_config_revision.revision"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_runtime_config_audit_revision_created",
        "runtime_config_audit_event",
        ["revision", "created_at"],
        unique=False,
    )
    op.execute(
        "INSERT INTO runtime_config_state "
        "(id, current_revision, current_fingerprint) VALUES (1, 0, NULL)"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_config_audit_revision_created",
        table_name="runtime_config_audit_event",
    )
    op.drop_table("runtime_config_audit_event")
    op.drop_table("runtime_config_state")
    op.drop_table("runtime_config_revision")
