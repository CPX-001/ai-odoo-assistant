"""Persist bounded XML and static ACL declaration metadata.

Revision ID: 0005_m3_05_xml_csv
Revises: 0004_m3_04_python_ast
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_m3_05_xml_csv"
down_revision: str | None = "0004_m3_04_python_ast"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_symbol",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "xml_record",
        sa.Column("declaration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("xml_record", "declaration")
    op.drop_column("source_symbol", "details")
