"""Minimal M1 runtime persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
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
    capabilities: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
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
