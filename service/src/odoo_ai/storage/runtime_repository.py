"""Concrete create/read operations required by M1 runtime status and tracing."""

import re
from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from odoo_ai.contracts import LogCapabilityState, SourceCapabilityState
from odoo_ai.storage.models import CapabilitySnapshot, InstanceProfile, TraceEvent

type Readiness = Literal["FULLY_READY", "DEGRADED", "ERROR"]
type ReasoningCapabilityState = Literal[
    "OPERATIONAL",
    "NOT_CONFIGURED",
    "RUNTIME_MISSING",
    "AUTH_UNAVAILABLE",
    "PROTOCOL_INCOMPATIBLE",
    "ERROR",
]

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
    capabilities: Mapping[str, JsonValue],
) -> CapabilitySnapshot:
    snapshot = CapabilitySnapshot(
        instance_profile_id=instance_profile_id,
        readiness=readiness,
        capabilities=dict(capabilities),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def record_source_capability(
    session: Session,
    *,
    instance_profile_id: UUID,
    state: SourceCapabilityState,
) -> CapabilitySnapshot:
    """Append a source state while preserving other known instance capabilities."""

    latest = get_latest_capability_snapshot(
        session, instance_profile_id=instance_profile_id
    )
    capabilities = dict(latest.capabilities) if latest is not None else {}
    capabilities["source"] = state.value
    capabilities["source_operational"] = state is SourceCapabilityState.DETECTED
    return create_capability_snapshot(
        session,
        instance_profile_id=instance_profile_id,
        readiness=_readiness_for_capabilities(capabilities),
        capabilities=capabilities,
    )


def record_log_capability(
    session: Session,
    *,
    instance_profile_id: UUID,
    state: LogCapabilityState,
    provider: str | None = None,
) -> CapabilitySnapshot:
    """Append a log-provider state while preserving other known capabilities."""

    latest = get_latest_capability_snapshot(
        session, instance_profile_id=instance_profile_id
    )
    capabilities = dict(latest.capabilities) if latest is not None else {}
    capabilities["logs"] = state.value
    capabilities["logs_operational"] = state is LogCapabilityState.OPERATIONAL
    if provider is not None:
        if provider not in {"file", "journal"}:
            raise ValueError("unsupported log provider")
        capabilities["log_provider"] = provider
    return create_capability_snapshot(
        session,
        instance_profile_id=instance_profile_id,
        readiness=_readiness_for_capabilities(capabilities),
        capabilities=capabilities,
    )


def record_reasoning_capability(
    session: Session,
    *,
    instance_profile_id: UUID,
    state: ReasoningCapabilityState,
    provider: Literal["codex"] = "codex",
    protocol: str | None = None,
    runtime_version: str | None = None,
    model: str | None = None,
) -> CapabilitySnapshot:
    """Append only the bounded reasoning facts allowed in capability snapshots."""

    safe_protocol = _safe_capability_text(protocol, max_length=64, field="protocol")
    safe_version = _safe_capability_text(
        runtime_version, max_length=64, field="runtime_version"
    )
    safe_model = _safe_capability_text(model, max_length=128, field="model")
    latest = get_latest_capability_snapshot(
        session, instance_profile_id=instance_profile_id
    )
    capabilities = dict(latest.capabilities) if latest is not None else {}
    capabilities.update(
        {
            "reasoning_engine": state,
            "reasoning_operational": state == "OPERATIONAL",
            "reasoning_provider": provider,
        }
    )
    optional = {
        "reasoning_protocol": safe_protocol,
        "reasoning_runtime_version": safe_version,
        "reasoning_model": safe_model,
    }
    for key, value in optional.items():
        if value is None:
            capabilities.pop(key, None)
        else:
            capabilities[key] = value
    readiness = _readiness_for_capabilities(capabilities)
    if (
        latest is not None
        and latest.readiness == readiness
        and latest.capabilities == capabilities
    ):
        return latest
    return create_capability_snapshot(
        session,
        instance_profile_id=instance_profile_id,
        readiness=readiness,
        capabilities=capabilities,
    )


def _readiness_for_capabilities(capabilities: Mapping[str, JsonValue]) -> Readiness:
    if (
        capabilities.get("source") == SourceCapabilityState.DETECTED.value
        and capabilities.get("logs") == LogCapabilityState.OPERATIONAL.value
        and capabilities.get("reasoning_engine") == "OPERATIONAL"
    ):
        return "FULLY_READY"
    return "DEGRADED"


def _safe_capability_text(
    value: str | None, *, max_length: int, field: str
) -> str | None:
    if value is None:
        return None
    if (
        not value
        or value != value.strip()
        or len(value) > max_length
        or any(character in value for character in "\r\n\0/\\")
    ):
        raise ValueError(f"unsafe reasoning {field}")
    return value


def get_latest_instance_profile(session: Session) -> InstanceProfile | None:
    return session.scalar(
        select(InstanceProfile)
        .order_by(InstanceProfile.updated_at.desc(), InstanceProfile.id.desc())
        .limit(1)
    )


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
