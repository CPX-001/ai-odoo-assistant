"""Add incremental knowledge documents, chunks, and PostgreSQL FTS.

Revision ID: 0006_m5_05_knowledge_fts
Revises: 0005_m3_05_xml_csv
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_m5_05_knowledge_fts"
down_revision: str | None = "0005_m3_05_xml_csv"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_profile_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("locale", sa.String(length=64), nullable=True),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="current", nullable=False
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_document_fingerprint",
        ),
        sa.CheckConstraint(
            "media_type IN ('text/plain', 'text/markdown')",
            name="ck_knowledge_document_media_type",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0", name="ck_knowledge_document_size_nonnegative"
        ),
        sa.CheckConstraint(
            "status IN ('current', 'retired')",
            name="ck_knowledge_document_status",
        ),
        sa.ForeignKeyConstraint(
            ["instance_profile_id"], ["instance_profile.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instance_profile_id",
            "provider_id",
            "document_id",
            name="uq_knowledge_document_logical_identity",
        ),
    )
    op.create_index(
        "ix_knowledge_document_fingerprint",
        "knowledge_document",
        ["fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_document_instance_provider_status",
        "knowledge_document",
        ["instance_profile_id", "provider_id", "status"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("document_fingerprint", sa.String(length=71), nullable=False),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("fts_config", sa.String(length=64), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            server_default=sa.text("''::tsvector"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "document_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunk_document_fingerprint",
        ),
        sa.CheckConstraint(
            "end_offset > start_offset", name="ck_knowledge_chunk_offset_range"
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunk_fingerprint",
        ),
        sa.CheckConstraint(
            "fts_config ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'",
            name="ck_knowledge_chunk_fts_config",
        ),
        sa.CheckConstraint(
            "start_line > 0 AND end_line >= start_line",
            name="ck_knowledge_chunk_line_range",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_knowledge_chunk_ordinal"),
        sa.CheckConstraint(
            "char_count > 0 AND byte_count > 0",
            name="ck_knowledge_chunk_sizes_positive",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_document_id"], ["knowledge_document.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_document_id",
            "ordinal",
            name="uq_knowledge_chunk_document_ordinal",
        ),
    )
    op.create_index(
        "ix_knowledge_chunk_document",
        "knowledge_chunk",
        ["knowledge_document_id", "ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_chunk_search_vector",
        "knowledge_chunk",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunk_search_vector", table_name="knowledge_chunk")
    op.drop_index("ix_knowledge_chunk_document", table_name="knowledge_chunk")
    op.drop_table("knowledge_chunk")
    op.drop_index(
        "ix_knowledge_document_instance_provider_status",
        table_name="knowledge_document",
    )
    op.drop_index("ix_knowledge_document_fingerprint", table_name="knowledge_document")
    op.drop_table("knowledge_document")
