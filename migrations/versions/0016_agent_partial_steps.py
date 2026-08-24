"""Allow partial outcomes for bounded batch plan steps.

Revision ID: 0016_agent_partial_steps
Revises: 0015_batch_mutation_jobs
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_agent_partial_steps"
down_revision: str | None = "0015_batch_mutation_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_plan_step_state",
        "agent_plan_step",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_plan_step_state",
        "agent_plan_step",
        "state IN ('planned','previewed','executing','completed','partial','failed','skipped')",
    )


def downgrade() -> None:
    # A partial row contains truthful execution history and must not be silently
    # coerced to failed/completed during downgrade.
    op.execute(
        "UPDATE agent_plan_step SET state = 'failed', "
        "error_code = COALESCE(error_code, 'downgraded_partial_step') "
        "WHERE state = 'partial'"
    )
    op.drop_constraint(
        "ck_agent_plan_step_state",
        "agent_plan_step",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_plan_step_state",
        "agent_plan_step",
        "state IN ('planned','previewed','executing','completed','failed','skipped')",
    )
