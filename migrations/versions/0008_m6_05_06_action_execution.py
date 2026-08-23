"""Add one-shot ACTION execution, verification, and sanitized audit facts.

Revision ID: 0008_m6_05_06_action_execution
Revises: 0007_m6_04_action_approvals
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_m6_05_06_action_execution"
down_revision: str | None = "0007_m6_04_action_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("action_proposal", sa.Column("attempt_id", sa.Uuid()))
    op.add_column(
        "action_proposal", sa.Column("execution_started_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "action_proposal", sa.Column("completed_at", sa.DateTime(timezone=True))
    )
    op.add_column("action_proposal", sa.Column("evidence_id", sa.Uuid()))
    op.add_column("action_proposal", sa.Column("error_code", sa.String(length=128)))
    op.add_column(
        "action_proposal",
        sa.Column("verification_payload", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.create_unique_constraint(
        "uq_action_proposal_attempt_id", "action_proposal", ["attempt_id"]
    )
    op.create_unique_constraint(
        "uq_action_proposal_evidence_id", "action_proposal", ["evidence_id"]
    )
    op.create_check_constraint(
        "ck_action_proposal_execution_shape",
        "action_proposal",
        "(state IN ('previewed', 'approved', 'rejected', 'expired') "
        "AND attempt_id IS NULL AND execution_started_at IS NULL "
        "AND completed_at IS NULL) OR "
        "(state = 'executing' AND attempt_id IS NOT NULL "
        "AND execution_started_at IS NOT NULL AND completed_at IS NULL) OR "
        "(state IN ('committed', 'verified', 'stale', 'failed', "
        "'execution_unknown', 'committed_unverified') "
        "AND attempt_id IS NOT NULL AND execution_started_at IS NOT NULL "
        "AND completed_at IS NOT NULL)",
    )
    op.create_table(
        "action_audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid()),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(event_type) > 0", name="ck_action_audit_event_type"
        ),
        sa.CheckConstraint("char_length(state) > 0", name="ck_action_audit_state"),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["action_proposal.proposal_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_audit_proposal_created",
        "action_audit_event",
        ["proposal_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_audit_proposal_created", table_name="action_audit_event")
    op.drop_table("action_audit_event")
    op.drop_constraint(
        "ck_action_proposal_execution_shape", "action_proposal", type_="check"
    )
    op.drop_constraint(
        "uq_action_proposal_evidence_id", "action_proposal", type_="unique"
    )
    op.drop_constraint(
        "uq_action_proposal_attempt_id", "action_proposal", type_="unique"
    )
    op.drop_column("action_proposal", "verification_payload")
    op.drop_column("action_proposal", "error_code")
    op.drop_column("action_proposal", "evidence_id")
    op.drop_column("action_proposal", "completed_at")
    op.drop_column("action_proposal", "execution_started_at")
    op.drop_column("action_proposal", "attempt_id")
