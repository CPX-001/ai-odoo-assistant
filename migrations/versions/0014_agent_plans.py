"""Persist unified agent plans and grouped authorizations.

Revision ID: 0014_agent_plans
Revises: 0013_chat_history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_agent_plans"
down_revision: str | None = "0013_chat_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
        "(action_kind = 'record_create' AND target_record_id IS NULL) OR "
        "(action_kind = 'business_action')",
    )
    op.drop_constraint(
        "ck_action_proposal_payload_size",
        "action_proposal",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_proposal_payload_size",
        "action_proposal",
        "octet_length(canonical_payload) BETWEEN 1 AND 24576",
    )
    op.create_table(
        "agent_plan",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("database", sa.String(length=128), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("allowed_company_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("goal", sa.String(length=1000), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=False),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("canonical_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("authorization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("authorization_source", sa.String(length=32), nullable=True),
        sa.Column("decided_by_uid", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("uid > 0 AND company_id > 0", name="ck_agent_plan_actor_positive"),
        sa.CheckConstraint(
            "state IN ('planning','awaiting_confirmation','authorized','executing',"
            "'completed','partial','failed','rejected','expired')",
            name="ck_agent_plan_state",
        ),
        sa.CheckConstraint(
            "risk IN ('low','moderate','high','protected')",
            name="ck_agent_plan_risk",
        ),
        sa.CheckConstraint(
            "plan_fingerprint ~ '^agent-plan:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_fingerprint",
        ),
        sa.CheckConstraint(
            "policy_fingerprint ~ '^agent-policy:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_policy_fingerprint",
        ),
        sa.CheckConstraint("state_version >= 0", name="ck_agent_plan_state_version"),
        sa.PrimaryKeyConstraint("plan_id"),
        sa.UniqueConstraint("turn_id"),
        sa.UniqueConstraint("plan_fingerprint"),
        sa.UniqueConstraint("authorization_id"),
    )
    op.create_index(
        "ix_agent_plan_actor_created",
        "agent_plan",
        ["database", "uid", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_plan_conversation_created",
        "agent_plan",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_plan_step",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dependencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk", sa.String(length=16), nullable=False),
        sa.Column("effect_scope", sa.String(length=32), nullable=False),
        sa.Column("is_write", sa.Boolean(), nullable=False),
        sa.Column("is_business_action", sa.Boolean(), nullable=False),
        sa.Column("atomic", sa.Boolean(), nullable=False),
        sa.Column("estimated_records", sa.Integer(), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0 AND position < 12", name="ck_agent_plan_step_position"),
        sa.CheckConstraint(
            "state IN ('planned','previewed','executing','completed','failed','skipped')",
            name="ck_agent_plan_step_state",
        ),
        sa.CheckConstraint(
            "risk IN ('low','moderate','high','protected')",
            name="ck_agent_plan_step_risk",
        ),
        sa.CheckConstraint(
            "effect_scope IN ('read_only','internal_reversible','internal_irreversible','external')",
            name="ck_agent_plan_step_effect_scope",
        ),
        sa.CheckConstraint(
            "payload_fingerprint ~ '^agent-step:v1:sha256:[0-9a-f]{64}$'",
            name="ck_agent_plan_step_fingerprint",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plan.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "position", name="uq_agent_plan_step_position"),
        sa.UniqueConstraint("plan_id", "step_id", name="uq_agent_plan_step_id"),
    )
    op.create_index(
        "ix_agent_plan_step_plan_state",
        "agent_plan_step",
        ["plan_id", "state"],
        unique=False,
    )

    op.create_table(
        "agent_plan_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("actor_uid", sa.Integer(), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("actor_uid > 0", name="ck_agent_plan_audit_actor_positive"),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plan.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_plan_audit_plan_created",
        "agent_plan_audit_event",
        ["plan_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_plan_audit_plan_created", table_name="agent_plan_audit_event")
    op.drop_table("agent_plan_audit_event")
    op.drop_index("ix_agent_plan_step_plan_state", table_name="agent_plan_step")
    op.drop_table("agent_plan_step")
    op.drop_index("ix_agent_plan_conversation_created", table_name="agent_plan")
    op.drop_index("ix_agent_plan_actor_created", table_name="agent_plan")
    op.drop_table("agent_plan")
    op.drop_constraint(
        "ck_action_proposal_payload_size",
        "action_proposal",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_proposal_payload_size",
        "action_proposal",
        "octet_length(canonical_payload) BETWEEN 1 AND 8192",
    )
    op.drop_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        type_="check",
    )
    op.create_check_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
        "(action_kind = 'record_create' AND target_record_id IS NULL) OR "
        "(action_kind = 'business_action' AND target_record_id IS NOT NULL)",
    )
