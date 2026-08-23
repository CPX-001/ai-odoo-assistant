"""Extend durable ACTION proposals for safe single-record create.

Revision ID: 0009_m6_11_record_create
Revises: 0008_m6_05_06_action_execution
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_m6_11_record_create"
down_revision: str | None = "0008_m6_05_06_action_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_proposal",
        sa.Column(
            "action_kind",
            sa.String(length=32),
            server_default="record_patch",
            nullable=False,
        ),
    )
    op.alter_column("action_proposal", "target_record_id", nullable=True)
    op.create_check_constraint(
        "ck_action_proposal_target_shape",
        "action_proposal",
        "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
        "(action_kind = 'record_create' AND target_record_id IS NULL)",
    )
    op.alter_column("action_proposal", "action_kind", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_action_proposal_target_shape", "action_proposal", type_="check"
    )
    op.execute("DELETE FROM action_proposal WHERE action_kind = 'record_create'")
    op.alter_column("action_proposal", "target_record_id", nullable=False)
    op.drop_column("action_proposal", "action_kind")
