"""Add durable canonical ACTION proposals and approval state.

Revision ID: 0007_m6_04_action_approvals
Revises: 0006_m5_05_knowledge_fts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_m6_04_action_approvals"
down_revision: str | None = "0006_m5_05_knowledge_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_proposal",
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("workflow", sa.String(length=16), nullable=False),
        sa.Column("instance_id", sa.String(length=255), nullable=False),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "allowed_company_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("target_model", sa.String(length=128), nullable=False),
        sa.Column("target_record_id", sa.Integer(), nullable=False),
        sa.Column("canonical_payload", sa.Text(), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("policy_revision", sa.String(length=128), nullable=False),
        sa.Column("schema_revision", sa.String(length=128), nullable=False),
        sa.Column("preview_id", sa.Uuid(), nullable=False),
        sa.Column(
            "preview_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("precondition_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            server_default="previewed",
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("decided_by_uid", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "octet_length(canonical_payload) BETWEEN 1 AND 8192",
            name="ck_action_proposal_payload_size",
        ),
        sa.CheckConstraint(
            "(state = 'previewed' AND decision IS NULL "
            "AND approval_id IS NULL AND decided_at IS NULL "
            "AND decided_by_uid IS NULL) OR "
            "(state = 'rejected' AND decision = 'reject' AND approval_id IS NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL) OR "
            "(state = 'expired' AND ((decision IS NULL AND approval_id IS NULL "
            "AND decided_at IS NULL AND decided_by_uid IS NULL) OR "
            "(decision = 'approve' AND approval_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL))) OR "
            "(state IN ('approved', 'executing', 'committed', 'verified', 'stale', "
            "'failed', 'execution_unknown', 'committed_unverified') "
            "AND decision = 'approve' AND approval_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL)",
            name="ck_action_proposal_decision_shape",
        ),
        sa.CheckConstraint(
            "format_version = 1", name="ck_action_proposal_format_version"
        ),
        sa.CheckConstraint(
            "payload_fingerprint ~ '^action-payload:v1:sha256:[0-9a-f]{64}$'",
            name="ck_action_proposal_payload_fingerprint",
        ),
        sa.CheckConstraint(
            "precondition_fingerprint ~ '^action-precondition:v1:sha256:[0-9a-f]{64}$'",
            name="ck_action_proposal_precondition_fingerprint",
        ),
        sa.CheckConstraint(
            "state IN ('previewed', 'approved', 'rejected', 'expired', "
            "'executing', 'committed', 'verified', 'stale', 'failed', "
            "'execution_unknown', 'committed_unverified')",
            name="ck_action_proposal_state",
        ),
        sa.CheckConstraint(
            "state_version >= 0", name="ck_action_proposal_state_version"
        ),
        sa.CheckConstraint("workflow = 'ACTION'", name="ck_action_proposal_workflow"),
        sa.PrimaryKeyConstraint("proposal_id"),
        sa.UniqueConstraint("approval_id"),
        sa.UniqueConstraint("payload_fingerprint"),
        sa.UniqueConstraint("preview_id"),
    )
    op.create_index(
        "ix_action_proposal_actor_state",
        "action_proposal",
        ["database", "uid", "state"],
        unique=False,
    )
    op.create_index(
        "ix_action_proposal_target_state",
        "action_proposal",
        ["target_model", "target_record_id", "state"],
        unique=False,
    )
    op.create_index(
        "ix_action_proposal_turn", "action_proposal", ["turn_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_action_proposal_turn", table_name="action_proposal")
    op.drop_index("ix_action_proposal_target_state", table_name="action_proposal")
    op.drop_index("ix_action_proposal_actor_state", table_name="action_proposal")
    op.drop_table("action_proposal")
