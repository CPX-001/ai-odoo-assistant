import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import JsonValue
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from odoo_ai.contracts import LogCapabilityState, SourceCapabilityState
from odoo_ai.storage import (
    DatabaseSettings,
    UnsafeTraceAttributesError,
    create_capability_snapshot,
    create_database_engine,
    create_instance_profile,
    create_trace_event,
    get_instance_profile,
    get_latest_capability_snapshot,
    list_trace_events,
    record_log_capability,
    record_source_capability,
)
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"


@pytest.fixture
def migrated_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")

    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    command.upgrade(Config(REPO_ROOT / "alembic.ini"), "head")

    engine = create_database_engine(DatabaseSettings.from_env())
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine) -> Session:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def test_runtime_tables_and_indexes_exist(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    assert {"instance_profile", "capability_snapshot", "trace_event"} <= set(
        inspector.get_table_names()
    )
    assert {index["name"] for index in inspector.get_indexes("capability_snapshot")} >= {
        "ix_capability_snapshot_instance_created"
    }
    assert {
        constraint["name"] for constraint in inspector.get_unique_constraints("trace_event")
    } >= {"uq_trace_event_trace_sequence"}


def test_create_and_read_instance_and_capability_snapshot(session: Session) -> None:
    instance_id = f"test-{uuid4()}"
    profile = create_instance_profile(
        session, instance_id=instance_id, fingerprint="sha256:instance"
    )
    snapshot = create_capability_snapshot(
        session,
        instance_profile_id=profile.id,
        readiness="DEGRADED",
        capabilities={"runtime_http": True, "assistant_db": True, "source": False},
    )

    loaded_profile = get_instance_profile(session, instance_id=instance_id)
    loaded_snapshot = get_latest_capability_snapshot(session, instance_profile_id=profile.id)

    assert loaded_profile is not None
    assert loaded_profile.id == profile.id
    assert loaded_snapshot is not None
    assert loaded_snapshot.id == snapshot.id
    assert loaded_snapshot.capabilities["assistant_db"] is True


def test_trace_events_are_ordered_and_reject_sensitive_attributes(session: Session) -> None:
    trace_id = uuid4()
    safe_attributes: dict[str, JsonValue] = {
        "tool_name": "health.probe",
        "latency_ms": 12,
        "token_usage": {"input": 3, "output": 1},
    }
    create_trace_event(
        session,
        trace_id=trace_id,
        sequence=1,
        event_name="tool.completed",
        status="ok",
        attributes=safe_attributes,
    )
    create_trace_event(
        session,
        trace_id=trace_id,
        sequence=0,
        event_name="tool.requested",
        status="ok",
    )

    assert [event.sequence for event in list_trace_events(session, trace_id=trace_id)] == [0, 1]

    with pytest.raises(UnsafeTraceAttributesError):
        create_trace_event(
            session,
            trace_id=trace_id,
            sequence=2,
            event_name="engine.failed",
            status="error",
            attributes={"nested": {"api_key": "must-not-be-stored"}},
        )

    with pytest.raises(IntegrityError), session.begin_nested():
        create_trace_event(
            session,
            trace_id=trace_id,
            sequence=1,
            event_name="tool.duplicate",
            status="error",
        )


def test_log_capability_preserves_source_and_distinguishes_readiness_states(
    session: Session,
) -> None:
    profile = create_instance_profile(
        session,
        instance_id=f"logs-{uuid4()}",
        fingerprint="sha256:logs",
    )
    record_source_capability(
        session,
        instance_profile_id=profile.id,
        state=SourceCapabilityState.DETECTED,
    )
    snapshot = record_log_capability(
        session,
        instance_profile_id=profile.id,
        state=LogCapabilityState.NO_PERMISSION,
    )

    assert snapshot.readiness == "DEGRADED"
    assert snapshot.capabilities["source"] == "DETECTED"
    assert snapshot.capabilities["logs"] == "NO_PERMISSION"
    assert snapshot.capabilities["logs_operational"] is False
