"""PostgreSQL persistence infrastructure for the Assistant Service."""

from odoo_ai.storage.base import Base
from odoo_ai.storage.config import DatabaseConfigurationError, DatabaseSettings
from odoo_ai.storage.database import create_database_engine, create_session_factory, session_scope
from odoo_ai.storage.models import CapabilitySnapshot, InstanceProfile, TraceEvent
from odoo_ai.storage.runtime_repository import (
    UnsafeTraceAttributesError,
    create_capability_snapshot,
    create_instance_profile,
    create_trace_event,
    get_instance_profile,
    get_latest_capability_snapshot,
    get_latest_instance_profile,
    list_trace_events,
)

__all__ = [
    "Base",
    "CapabilitySnapshot",
    "DatabaseConfigurationError",
    "DatabaseSettings",
    "InstanceProfile",
    "TraceEvent",
    "UnsafeTraceAttributesError",
    "create_capability_snapshot",
    "create_database_engine",
    "create_instance_profile",
    "create_session_factory",
    "create_trace_event",
    "get_instance_profile",
    "get_latest_capability_snapshot",
    "get_latest_instance_profile",
    "list_trace_events",
    "session_scope",
]
