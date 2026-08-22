"""Persist conservative provenance and extractor metadata.

Revision ID: 0004_m3_04_python_ast
Revises: 0003_m3_02_source_index
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_m3_04_python_ast"
down_revision: str | None = "0003_m3_02_source_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_file",
        sa.Column(
            "provenance",
            sa.String(length=64),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "source_file",
        sa.Column("extracted_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_source_file_provenance",
        "source_file",
        "provenance IN ('official', 'oca', 'remote_known', 'manual', "
        "'third_party_or_custom', 'unknown')",
    )
    op.alter_column("source_file", "provenance", server_default=None)

    op.drop_constraint(
        "uq_source_symbol_file_identity", "source_symbol", type_="unique"
    )
    op.create_unique_constraint(
        "uq_source_symbol_file_identity",
        "source_symbol",
        ["source_file_id", "kind", "model", "name", "start_line", "end_line"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_source_symbol_file_identity", "source_symbol", type_="unique"
    )
    op.create_unique_constraint(
        "uq_source_symbol_file_identity",
        "source_symbol",
        ["source_file_id", "kind", "name", "start_line", "end_line"],
    )
    op.drop_constraint("ck_source_file_provenance", "source_file", type_="check")
    op.drop_column("source_file", "extracted_metadata")
    op.drop_column("source_file", "provenance")
