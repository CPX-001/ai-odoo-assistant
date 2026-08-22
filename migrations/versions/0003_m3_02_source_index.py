"""Add incremental source scan and index persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_m3_02_source_index"
down_revision: str | None = "0002_m1_03_runtime_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_profile_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=71), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) OR "
            "(status <> 'running' AND completed_at IS NOT NULL)",
            name="ck_scan_run_completion",
        ),
        sa.CheckConstraint(
            "fingerprint IS NULL OR fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_scan_run_fingerprint",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_scan_run_status",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR error_code IS NULL",
            name="ck_scan_run_success_error",
        ),
        sa.ForeignKeyConstraint(
            ["instance_profile_id"], ["instance_profile.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scan_run_instance_status_started",
        "scan_run",
        ["instance_profile_id", "status", "started_at"],
        unique=False,
    )

    op.create_table(
        "source_file",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_profile_id", sa.Uuid(), nullable=False),
        sa.Column("scan_run_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=255), nullable=False),
        sa.Column("logical_path", sa.String(length=1024), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "is_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
            name="ck_source_file_fingerprint",
        ),
        sa.CheckConstraint(
            "kind IN ('manifest', 'python', 'xml', 'csv', 'other')",
            name="ck_source_file_kind",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_source_file_size_nonnegative"),
        sa.ForeignKeyConstraint(
            ["instance_profile_id"], ["instance_profile.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["scan_run_id"], ["scan_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instance_profile_id",
            "module",
            "logical_path",
            name="uq_source_file_instance_module_path",
        ),
    )
    op.create_index(
        "ix_source_file_fingerprint", "source_file", ["fingerprint"], unique=False
    )
    op.create_index(
        "ix_source_file_instance_module",
        "source_file",
        ["instance_profile_id", "module"],
        unique=False,
    )

    op.create_table(
        "source_symbol",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("logical_path", sa.String(length=1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.CheckConstraint(
            "end_line >= start_line", name="ck_source_symbol_line_range"
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_source_symbol_fingerprint",
        ),
        sa.CheckConstraint("start_line > 0", name="ck_source_symbol_start_line"),
        sa.ForeignKeyConstraint(
            ["source_file_id"], ["source_file.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_file_id",
            "kind",
            "name",
            "start_line",
            "end_line",
            name="uq_source_symbol_file_identity",
        ),
    )
    op.create_index(
        "ix_source_symbol_model_name",
        "source_symbol",
        ["model", "name"],
        unique=False,
    )
    op.create_index(
        "ix_source_symbol_module_path",
        "source_symbol",
        ["module", "logical_path"],
        unique=False,
    )

    op.create_table(
        "xml_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=255), nullable=False),
        sa.Column("xml_id", sa.String(length=512), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("logical_path", sa.String(length=1024), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=71), nullable=False),
        sa.CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_xml_record_fingerprint",
        ),
        sa.CheckConstraint(
            "(start_line IS NULL AND end_line IS NULL) OR "
            "(start_line > 0 AND end_line >= start_line)",
            name="ck_xml_record_line_range",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"], ["source_file.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_file_id", "xml_id", name="uq_xml_record_file_xml_id"
        ),
    )
    op.create_index(
        "ix_xml_record_module_path",
        "xml_record",
        ["module", "logical_path"],
        unique=False,
    )
    op.create_index(
        "ix_xml_record_xml_id_model",
        "xml_record",
        ["xml_id", "model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_xml_record_xml_id_model", table_name="xml_record")
    op.drop_index("ix_xml_record_module_path", table_name="xml_record")
    op.drop_table("xml_record")
    op.drop_index("ix_source_symbol_module_path", table_name="source_symbol")
    op.drop_index("ix_source_symbol_model_name", table_name="source_symbol")
    op.drop_table("source_symbol")
    op.drop_index("ix_source_file_instance_module", table_name="source_file")
    op.drop_index("ix_source_file_fingerprint", table_name="source_file")
    op.drop_table("source_file")
    op.drop_index("ix_scan_run_instance_status_started", table_name="scan_run")
    op.drop_table("scan_run")
