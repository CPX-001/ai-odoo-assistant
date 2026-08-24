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
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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


class ActionProposalRecord(Base):
    """Immutable canonical ACTION proposal with a closed mutable lifecycle."""

    __tablename__ = "action_proposal"
    __table_args__ = (
        CheckConstraint("workflow = 'ACTION'", name="ck_action_proposal_workflow"),
        CheckConstraint("format_version = 1", name="ck_action_proposal_format_version"),
        CheckConstraint(
            "(action_kind = 'record_patch' AND target_record_id IS NOT NULL) OR "
            "(action_kind = 'record_create' AND target_record_id IS NULL) OR "
            "(action_kind = 'business_action')",
            name="ck_action_proposal_target_shape",
        ),
        CheckConstraint(
            "state IN ('previewed', 'approved', 'rejected', 'expired', "
            "'executing', 'committed', 'verified', 'stale', 'failed', "
            "'execution_unknown', 'committed_unverified')",
            name="ck_action_proposal_state",
        ),
        CheckConstraint(
            "payload_fingerprint ~ '^action-payload:v1:sha256:[0-9a-f]{64}$'",
            name="ck_action_proposal_payload_fingerprint",
        ),
        CheckConstraint(
            "precondition_fingerprint ~ '^action-precondition:v1:sha256:[0-9a-f]{64}$'",
            name="ck_action_proposal_precondition_fingerprint",
        ),
        CheckConstraint(
            "octet_length(canonical_payload) BETWEEN 1 AND 24576",
            name="ck_action_proposal_payload_size",
        ),
        CheckConstraint("state_version >= 0", name="ck_action_proposal_state_version"),
        CheckConstraint(
            "(state IN ('previewed', 'approved', 'rejected', 'expired') "
            "AND attempt_id IS NULL AND execution_started_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(state = 'executing' AND attempt_id IS NOT NULL "
            "AND execution_started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(state IN ('committed', 'verified', 'stale', 'failed', "
            "'execution_unknown', 'committed_unverified') "
            "AND attempt_id IS NOT NULL AND execution_started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_action_proposal_execution_shape",
        ),
        CheckConstraint(
            "(state = 'previewed' AND decision IS NULL "
            "AND approval_id IS NULL AND decided_at IS NULL "
            "AND decided_by_uid IS NULL) OR "
            "(state = 'rejected' AND decision = 'reject' AND approval_id IS NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL) OR "
            "(state = 'expired' AND ((decision IS NULL AND approval_id IS NULL "
            "AND decided_at IS NULL AND decided_by_uid IS NULL) OR "
            "(decision = 'approve' AND approval_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL))) OR "
            "(state IN ('approved', 'executing', 'committed', 'verified', 'stale', "
            "'failed', 'execution_unknown', 'committed_unverified') "
            "AND decision = 'approve' AND approval_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_by_uid IS NOT NULL)",
            name="ck_action_proposal_decision_shape",
        ),
        Index("ix_action_proposal_turn", "turn_id"),
        Index(
            "ix_action_proposal_actor_state",
            "database",
            "uid",
            "state",
        ),
        Index(
            "ix_action_proposal_target_state",
            "target_model",
            "target_record_id",
            "state",
        ),
    )

    proposal_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    turn_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    workflow: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTION")
    instance_id: Mapped[str] = mapped_column(String(255), nullable=False)
    database: Mapped[str] = mapped_column(String(128), nullable=False)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_company_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    target_record_id: Mapped[int | None] = mapped_column(Integer)
    canonical_payload: Mapped[str] = mapped_column(Text, nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    policy_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    preview_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    preview_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    precondition_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    previewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="previewed", server_default="previewed"
    )
    decision: Mapped[str | None] = mapped_column(String(16))
    decided_by_uid: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    attempt_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    error_code: Mapped[str | None] = mapped_column(String(128))
    verification_payload: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionAuditRecord(Base):
    """Append-only sanitized ACTION lifecycle fact."""

    __tablename__ = "action_audit_event"
    __table_args__ = (
        CheckConstraint("char_length(event_type) > 0", name="ck_action_audit_event_type"),
        CheckConstraint("char_length(state) > 0", name="ck_action_audit_state"),
        Index("ix_action_audit_proposal_created", "proposal_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("action_proposal.proposal_id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[UUID | None] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
        UniqueConstraint("source_file_id", "xml_id", name="uq_xml_record_file_xml_id"),
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


class KnowledgeDocument(Base):
    """Current or retired version of one logical configured document."""

    __tablename__ = "knowledge_document"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_knowledge_document_size_nonnegative"),
        CheckConstraint(
            "media_type IN ('text/plain', 'text/markdown')",
            name="ck_knowledge_document_media_type",
        ),
        CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_document_fingerprint",
        ),
        CheckConstraint(
            "status IN ('current', 'retired')",
            name="ck_knowledge_document_status",
        ),
        UniqueConstraint(
            "instance_profile_id",
            "provider_id",
            "document_id",
            name="uq_knowledge_document_logical_identity",
        ),
        Index(
            "ix_knowledge_document_instance_provider_status",
            "instance_profile_id",
            "provider_id",
            "status",
        ),
        Index("ix_knowledge_document_fingerprint", "fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    instance_profile_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("instance_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
    )


class KnowledgeChunk(Base):
    """Bounded current-version text chunk with a PostgreSQL FTS vector."""

    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ck_knowledge_chunk_ordinal"),
        CheckConstraint(
            "document_fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunk_document_fingerprint",
        ),
        CheckConstraint(
            "fingerprint ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunk_fingerprint",
        ),
        CheckConstraint(
            "end_offset > start_offset",
            name="ck_knowledge_chunk_offset_range",
        ),
        CheckConstraint(
            "start_line > 0 AND end_line >= start_line",
            name="ck_knowledge_chunk_line_range",
        ),
        CheckConstraint(
            "char_count > 0 AND byte_count > 0",
            name="ck_knowledge_chunk_sizes_positive",
        ),
        CheckConstraint(
            "fts_config ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'",
            name="ck_knowledge_chunk_fts_config",
        ),
        UniqueConstraint(
            "knowledge_document_id",
            "ordinal",
            name="uq_knowledge_chunk_document_ordinal",
        ),
        Index("ix_knowledge_chunk_document", "knowledge_document_id", "ordinal"),
        Index(
            "ix_knowledge_chunk_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    knowledge_document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    document_fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(71), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fts_config: Mapped[str] = mapped_column(String(64), nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, nullable=False, server_default="''::tsvector"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
