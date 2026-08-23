"""Allow durable proposals for the curated M6 business action.

Revision ID: 0010_m6_12_business_action
Revises: 0009_m6_11_record_create
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_m6_12_business_action"
down_revision: str | None = "0009_m6_11_record_create"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_action_proposal_target_shape", "action_proposal", type_="check"
    )
    op.create_check_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
        "(action_kind = 'record_create' AND target_record_id IS NULL) OR "
        "(action_kind = 'business_action' AND target_record_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM action_proposal WHERE action_kind = 'business_action'")
    op.drop_constraint(
        "ck_action_proposal_target_shape", "action_proposal", type_="check"
    )
    op.create_check_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
        "(action_kind = 'record_create' AND target_record_id IS NULL)",
    )
