"""Minimal M1 runtime persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from odoo_ai.storage.base import Base


class InstanceProfile(Base):
    """Current fingerprint for one detected Assistant installation."""

    __tablename__ = "instance_profile"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    instance_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )


class CapabilitySnapshot(Base):
    """Point-in-time runtime capabilities and readiness for an instance."""

    __tablename__ = "capability_snapshot"
    __table_args__ = (
        CheckConstraint(
            "readiness IN ('FULLY_READY', 'DEGRADED', 'ERROR')",
            name="ck_capability_snapshot_readiness",
        ),
        Index("ix_capability_snapshot_instance_created", "instance_profile_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    instance_profile_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("instance_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    readiness: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )


class TraceEvent(Base):
    """Sanitized technical event in an ordered logical trace."""

    __tablename__ = "trace_event"
    __table_args__ = (
        CheckConstraint("sequence >= 0", name="ck_trace_event_sequence_nonnegative"),
        CheckConstraint("char_length(event_name) > 0", name="ck_trace_event_name_nonempty"),
        CheckConstraint("char_length(status) > 0", name="ck_trace_event_status_nonempty"),
        UniqueConstraint("trace_id", "sequence", name="uq_trace_event_trace_sequence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )


class ScanRun(Base):
    """Lifecycle and aggregate fingerprint for one bounded source scan."""

    __tablename__ = "scan_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_scan_run_status",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) OR "
            "(status <> 'running' AND completed_at IS NOT NULL)",
            name="ck_scan_run_completion",
        ),
        CheckConstraint(
            "fingerprint IS NULL OR fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_scan_run_fingerprint",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR error_code IS NULL",
            name="ck_scan_run_success_error",
        ),
        Index(
            "ix_scan_run_instance_status_started",
            "instance_profile_id",
            "status",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    instance_profile_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("instance_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str | None] = mapped_column(String(71))
    error_code: Mapped[str | None] = mapped_column(String(128))


class SourceFile(Base):
    """Current metadata for one indexed source file."""

    __tablename__ = "source_file"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_source_file_size_nonnegative"),
        CheckConstraint(
            "kind IN ('manifest', 'python', 'xml', 'csv', 'other')",
            name="ck_source_file_kind",
        ),
        CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_source_file_fingerprint",
        ),
        CheckConstraint(
            "provenance IN ('official', 'oca', 'remote_known', 'manual', "
            "'third_party_or_custom', 'unknown')",
            name="ck_source_file_provenance",
        ),
        UniqueConstraint(
            "instance_profile_id",
            "module",
            "logical_path",
            name="uq_source_file_instance_module_path",
        ),
        Index("ix_source_file_instance_module", "instance_profile_id", "module"),
        Index("ix_source_file_fingerprint", "fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    instance_profile_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("instance_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    scan_run_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("scan_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    logical_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provenance: Mapped[str] = mapped_column(
        String(64), nullable=False, default="unknown", server_default="unknown"
    )
    extracted_metadata: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )


class SourceSymbol(Base):
    """A source symbol derived from the current fingerprint of one file."""

    __tablename__ = "source_symbol"
    __table_args__ = (
        CheckConstraint("start_line > 0", name="ck_source_symbol_start_line"),
        CheckConstraint("end_line >= start_line", name="ck_source_symbol_line_range"),
        CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_source_symbol_fingerprint",
        ),
        UniqueConstraint(
            "source_file_id",
            "kind",
            "model",
            "name",
            "start_line",
            "end_line",
            name="uq_source_symbol_file_identity",
        ),
        Index("ix_source_symbol_model_name", "model", "name"),
        Index("ix_source_symbol_module_path", "module", "logical_path"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_file_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_file.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logical_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    details: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)


class XmlRecord(Base):
    """An XML record declaration derived from one source file."""

    __tablename__ = "xml_record"
    __table_args__ = (
        CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_xml_record_fingerprint",
        ),
        CheckConstraint(
            "(start_line IS NULL AND end_line IS NULL) OR "
            "(start_line > 0 AND end_line >= start_line)",
            name="ck_xml_record_line_range",
        ),
        UniqueConstraint(
            "source_file_id", "xml_id", name="uq_xml_record_file_xml_id"
        ),
        Index("ix_xml_record_xml_id_model", "xml_id", "model"),
        Index("ix_xml_record_module_path", "module", "logical_path"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_file_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("source_file.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    xml_id: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255))
    logical_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    declaration: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
