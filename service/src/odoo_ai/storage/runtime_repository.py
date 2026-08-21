"""Concrete create/read operations required by M1 runtime status and tracing."""

import re
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from odoo_ai.storage.models import CapabilitySnapshot, InstanceProfile, TraceEvent

type Readiness = Literal["FULLY_READY", "DEGRADED", "ERROR"]

_SENSITIVE_KEY_PARTS = ("password", "secret", "api_key", "authorization", "cookie")
_SENSITIVE_KEYS = {
    "access_token",
    "id_token",
    "messages",
    "prompt",
    "raw_config",
    "raw_messages",
    "refresh_token",
    "system_prompt",
    "token",
}


class UnsafeTraceAttributesError(ValueError):
    """Raised when trace metadata may contain secrets or raw prompt content."""


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


def _validate_trace_value(value: JsonValue) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized = _normalize_key(key)
            if normalized in _SENSITIVE_KEYS or any(
                marker in normalized for marker in _SENSITIVE_KEY_PARTS
            ):
                raise UnsafeTraceAttributesError(
                    "Trace attributes contain a forbidden sensitive field"
                )
            _validate_trace_value(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _validate_trace_value(nested_value)


def create_instance_profile(
    session: Session, *, instance_id: str, fingerprint: str
) -> InstanceProfile:
    profile = InstanceProfile(instance_id=instance_id, fingerprint=fingerprint)
    session.add(profile)
    session.flush()
    return profile


def get_instance_profile(session: Session, *, instance_id: str) -> InstanceProfile | None:
    return session.scalar(select(InstanceProfile).where(InstanceProfile.instance_id == instance_id))


def create_capability_snapshot(
    session: Session,
    *,
    instance_profile_id: UUID,
    readiness: Readiness,
    capabilities: Mapping[str, bool],
) -> CapabilitySnapshot:
    snapshot = CapabilitySnapshot(
        instance_profile_id=instance_profile_id,
        readiness=readiness,
        capabilities=dict(capabilities),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def get_latest_capability_snapshot(
    session: Session, *, instance_profile_id: UUID
) -> CapabilitySnapshot | None:
    return session.scalar(
        select(CapabilitySnapshot)
        .where(CapabilitySnapshot.instance_profile_id == instance_profile_id)
        .order_by(CapabilitySnapshot.created_at.desc(), CapabilitySnapshot.id.desc())
        .limit(1)
    )


def create_trace_event(
    session: Session,
    *,
    trace_id: UUID,
    sequence: int,
    event_name: str,
    status: str,
    attributes: Mapping[str, JsonValue] | None = None,
) -> TraceEvent:
    safe_attributes = dict(attributes or {})
    _validate_trace_value(safe_attributes)
    event = TraceEvent(
        trace_id=trace_id,
        sequence=sequence,
        event_name=event_name,
        status=status,
        attributes=safe_attributes,
    )
    session.add(event)
    session.flush()
    return event


def list_trace_events(session: Session, *, trace_id: UUID) -> list[TraceEvent]:
    return list(
        session.scalars(
            select(TraceEvent).where(TraceEvent.trace_id == trace_id).order_by(TraceEvent.sequence)
        )
    )
