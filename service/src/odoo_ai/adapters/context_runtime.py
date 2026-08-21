"""Assistant-owned storage adapters for the contextual read workflow."""

from typing import cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.application import TraceEventData
from odoo_ai.contracts import InstanceProfileSummary
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    create_trace_event,
    get_latest_capability_snapshot,
    get_latest_instance_profile,
    session_scope,
)


def load_instance_summary() -> InstanceProfileSummary:
    """Load compact Assistant-owned runtime facts or preserve explicit unknown."""

    engine = None
    try:
        engine = create_database_engine(DatabaseSettings.from_env())
        session_factory = create_session_factory(engine)
        with session_scope(session_factory) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                return InstanceProfileSummary(instance_id="unknown")
            snapshot = get_latest_capability_snapshot(
                session, instance_profile_id=profile.id
            )
            capabilities = (
                sorted(
                    name
                    for name, available in snapshot.capabilities.items()
                    if available
                )
                if snapshot is not None
                else []
            )
            return InstanceProfileSummary(
                instance_id=profile.instance_id,
                profile_revision=profile.fingerprint,
                capabilities=capabilities,
            )
    except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
        return InstanceProfileSummary(instance_id="unknown")
    finally:
        if engine is not None:
            engine.dispose()


def persist_trace_events(
    trace_id: UUID, events: tuple[TraceEventData, ...]
) -> None:
    """Best-effort persistence of metadata-only turn events in the Assistant DB."""

    engine = None
    try:
        engine = create_database_engine(DatabaseSettings.from_env())
        session_factory = create_session_factory(engine)
        with session_scope(session_factory) as session:
            for sequence, event in enumerate(events):
                create_trace_event(
                    session,
                    trace_id=trace_id,
                    sequence=sequence,
                    event_name=event.event_name,
                    status=event.status,
                    attributes=cast(dict[str, JsonValue], dict(event.attributes)),
                )
    except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
        return
    finally:
        if engine is not None:
            engine.dispose()
