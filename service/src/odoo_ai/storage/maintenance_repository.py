"""Persistence for the small allowlisted M7 maintenance surface."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from odoo_ai.contracts.maintenance import MaintenanceMetrics

_metadata = MetaData()

_maintenance_job = Table(
    "maintenance_job",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("operation", String(64), nullable=False),
    Column("state", String(16), nullable=False),
    Column("actor_uid", Integer, nullable=False),
    Column("actor_database", String(128), nullable=False),
    Column("result_code", String(128)),
    Column("metrics", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
)

_maintenance_audit_event = Table(
    "maintenance_audit_event",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("operation", String(64), nullable=False),
    Column("state", String(16), nullable=False),
    Column("actor_uid", Integer, nullable=False),
    Column("actor_database", String(128), nullable=False),
    Column("job_id", PGUUID(as_uuid=True)),
    Column("result_code", String(128)),
    Column("metrics", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_JOB_OPERATIONS = frozenset({"source_rescan", "knowledge_reindex"})
_ALL_OPERATIONS = frozenset(
    {
        "readiness_test",
        "source_rescan",
        "source_test",
        "logs_test",
        "knowledge_reindex",
        "reasoning_test",
        "configuration_revalidate",
    }
)
_STATES = frozenset({"queued", "running", "succeeded", "failed"})


class MaintenanceStoreError(RuntimeError):
    """Sanitized persistence error for maintenance state."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class MaintenanceJobRecord:
    job_id: UUID
    operation: str
    state: str
    actor_uid: int
    actor_database: str
    result_code: str | None
    metrics: dict[str, JsonValue]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class MaintenanceEventRecord:
    operation: str
    state: str
    actor_uid: int
    actor_database: str
    result_code: str | None
    metrics: dict[str, JsonValue]
    created_at: datetime
    job_id: UUID | None


def create_maintenance_job(
    session: Session,
    *,
    operation: str,
    actor_uid: int,
    actor_database: str,
) -> MaintenanceJobRecord:
    """Create one queued job while rejecting concurrent duplicates."""

    _validate_job_operation(operation)
    _validate_actor(actor_uid, actor_database)
    _expire_stale_jobs(session)
    job_id = uuid4()
    row = session.execute(
        pg_insert(_maintenance_job)
        .values(
            id=job_id,
            operation=operation,
            state="queued",
            actor_uid=actor_uid,
            actor_database=actor_database,
            metrics={},
        )
        .on_conflict_do_nothing()
        .returning(*_maintenance_job.c)
    ).mappings().one_or_none()
    if row is None:
        raise MaintenanceStoreError("maintenance_job_active")
    record = _job_record(row)
    record_maintenance_event(
        session,
        operation=operation,
        state="queued",
        actor_uid=actor_uid,
        actor_database=actor_database,
        job_id=job_id,
    )
    session.flush()
    return record


def mark_maintenance_job_running(session: Session, *, job_id: UUID) -> MaintenanceJobRecord:
    row = session.execute(
        update(_maintenance_job)
        .where(
            _maintenance_job.c.id == job_id,
            _maintenance_job.c.state == "queued",
        )
        .values(state="running", started_at=func.clock_timestamp())
        .returning(*_maintenance_job.c)
    ).mappings().one_or_none()
    if row is None:
        raise MaintenanceStoreError("maintenance_job_not_runnable")
    record = _job_record(row)
    record_maintenance_event(
        session,
        operation=record.operation,
        state="running",
        actor_uid=record.actor_uid,
        actor_database=record.actor_database,
        job_id=record.job_id,
    )
    session.flush()
    return record


def finish_maintenance_job(
    session: Session,
    *,
    job_id: UUID,
    succeeded: bool,
    result_code: str,
    metrics: MaintenanceMetrics | Mapping[str, JsonValue] | None = None,
) -> MaintenanceJobRecord:
    if not result_code or len(result_code) > 128:
        raise MaintenanceStoreError("maintenance_result_invalid")
    serialized = _metrics(metrics)
    state = "succeeded" if succeeded else "failed"
    row = session.execute(
        update(_maintenance_job)
        .where(
            _maintenance_job.c.id == job_id,
            _maintenance_job.c.state == "running",
        )
        .values(
            state=state,
            result_code=result_code,
            metrics=serialized,
            completed_at=func.clock_timestamp(),
        )
        .returning(*_maintenance_job.c)
    ).mappings().one_or_none()
    if row is None:
        raise MaintenanceStoreError("maintenance_job_not_running")
    record = _job_record(row)
    record_maintenance_event(
        session,
        operation=record.operation,
        state=state,
        actor_uid=record.actor_uid,
        actor_database=record.actor_database,
        job_id=record.job_id,
        result_code=result_code,
        metrics=serialized,
    )
    session.flush()
    return record


def get_maintenance_job(session: Session, *, job_id: UUID) -> MaintenanceJobRecord:
    row = session.execute(
        select(_maintenance_job).where(_maintenance_job.c.id == job_id)
    ).mappings().one_or_none()
    if row is None:
        raise MaintenanceStoreError("maintenance_job_not_found")
    return _job_record(row)


def list_active_maintenance_jobs(session: Session) -> tuple[MaintenanceJobRecord, ...]:
    rows = session.execute(
        select(_maintenance_job)
        .where(_maintenance_job.c.state.in_(("queued", "running")))
        .order_by(_maintenance_job.c.created_at.asc())
        .limit(2)
    ).mappings()
    return tuple(_job_record(row) for row in rows)


def record_maintenance_event(
    session: Session,
    *,
    operation: str,
    state: str,
    actor_uid: int,
    actor_database: str,
    result_code: str | None = None,
    metrics: MaintenanceMetrics | Mapping[str, JsonValue] | None = None,
    job_id: UUID | None = None,
) -> None:
    _validate_operation(operation)
    if state not in _STATES:
        raise MaintenanceStoreError("maintenance_state_invalid")
    _validate_actor(actor_uid, actor_database)
    if state in {"queued", "running"}:
        if result_code is not None:
            raise MaintenanceStoreError("maintenance_result_invalid")
    elif not result_code or len(result_code) > 128:
        raise MaintenanceStoreError("maintenance_result_invalid")
    session.execute(
        insert(_maintenance_audit_event).values(
            operation=operation,
            state=state,
            actor_uid=actor_uid,
            actor_database=actor_database,
            job_id=job_id,
            result_code=result_code,
            metrics=_metrics(metrics),
        )
    )


def list_latest_maintenance_events(
    session: Session,
) -> tuple[MaintenanceEventRecord, ...]:
    """Return only the latest event for each currently supported operation."""

    rows = session.execute(
        select(_maintenance_audit_event)
        .order_by(_maintenance_audit_event.c.id.desc())
        .limit(128)
    ).mappings()
    latest: list[MaintenanceEventRecord] = []
    seen: set[str] = set()
    for row in rows:
        operation = cast(str, row["operation"])
        if operation not in _ALL_OPERATIONS or operation in seen:
            continue
        seen.add(operation)
        latest.append(_event_record(row))
        if len(latest) == len(_ALL_OPERATIONS):
            break
    return tuple(latest)


def _expire_stale_jobs(session: Session) -> None:
    rows = session.execute(
        update(_maintenance_job)
        .where(
            _maintenance_job.c.state.in_(("queued", "running")),
            _maintenance_job.c.created_at
            < func.clock_timestamp() - text("interval '15 minutes'"),
        )
        .values(
            state="failed",
            result_code="maintenance_job_abandoned",
            started_at=func.coalesce(
                _maintenance_job.c.started_at,
                _maintenance_job.c.created_at,
            ),
            completed_at=func.clock_timestamp(),
        )
        .returning(*_maintenance_job.c)
    ).mappings()
    for row in rows:
        record = _job_record(row)
        record_maintenance_event(
            session,
            operation=record.operation,
            state="failed",
            actor_uid=record.actor_uid,
            actor_database=record.actor_database,
            job_id=record.job_id,
            result_code="maintenance_job_abandoned",
            metrics=record.metrics,
        )


def _metrics(
    value: MaintenanceMetrics | Mapping[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    if value is None:
        return {}
    model = value if isinstance(value, MaintenanceMetrics) else MaintenanceMetrics.model_validate(value)
    return cast(dict[str, JsonValue], model.model_dump(mode="json", exclude_none=True))


def _job_record(row: RowMapping) -> MaintenanceJobRecord:
    operation = cast(str, row["operation"])
    state = cast(str, row["state"])
    _validate_job_operation(operation)
    if state not in _STATES:
        raise MaintenanceStoreError("maintenance_state_invalid")
    return MaintenanceJobRecord(
        job_id=cast(UUID, row["id"]),
        operation=operation,
        state=state,
        actor_uid=cast(int, row["actor_uid"]),
        actor_database=cast(str, row["actor_database"]),
        result_code=cast(str | None, row["result_code"]),
        metrics=_metrics_mapping(row["metrics"]),
        created_at=cast(datetime, row["created_at"]),
        started_at=cast(datetime | None, row["started_at"]),
        completed_at=cast(datetime | None, row["completed_at"]),
    )


def _event_record(row: RowMapping) -> MaintenanceEventRecord:
    operation = cast(str, row["operation"])
    state = cast(str, row["state"])
    _validate_operation(operation)
    if state not in _STATES:
        raise MaintenanceStoreError("maintenance_state_invalid")
    return MaintenanceEventRecord(
        operation=operation,
        state=state,
        actor_uid=cast(int, row["actor_uid"]),
        actor_database=cast(str, row["actor_database"]),
        result_code=cast(str | None, row["result_code"]),
        metrics=_metrics_mapping(row["metrics"]),
        created_at=cast(datetime, row["created_at"]),
        job_id=cast(UUID | None, row["job_id"]),
    )


def _metrics_mapping(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise MaintenanceStoreError("maintenance_metrics_invalid")
    validated = MaintenanceMetrics.model_validate(value)
    return cast(
        dict[str, JsonValue],
        validated.model_dump(mode="json", exclude_none=True),
    )


def _validate_actor(actor_uid: int, actor_database: str) -> None:
    if actor_uid <= 0 or not actor_database or len(actor_database) > 128:
        raise MaintenanceStoreError("maintenance_actor_invalid")
    if any(character in actor_database for character in "\r\n\x00"):
        raise MaintenanceStoreError("maintenance_actor_invalid")


def _validate_job_operation(operation: str) -> None:
    if operation not in _JOB_OPERATIONS:
        raise MaintenanceStoreError("maintenance_operation_invalid")


def _validate_operation(operation: str) -> None:
    if operation not in _ALL_OPERATIONS:
        raise MaintenanceStoreError("maintenance_operation_invalid")
