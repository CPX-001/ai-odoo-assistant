"""Establish the Assistant database migration baseline."""

from collections.abc import Sequence

revision: str = "0001_m1_02_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record the empty M1-02 baseline without functional tables."""


def downgrade() -> None:
    """The baseline has no schema objects to remove."""
