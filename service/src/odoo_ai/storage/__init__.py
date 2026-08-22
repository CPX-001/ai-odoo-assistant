"""PostgreSQL persistence infrastructure for the Assistant Service."""

from odoo_ai.storage.base import Base
from odoo_ai.storage.config import DatabaseConfigurationError, DatabaseSettings
from odoo_ai.storage.database import create_database_engine, create_session_factory, session_scope
from odoo_ai.storage.models import (
    CapabilitySnapshot,
    InstanceProfile,
    ScanRun,
    SourceFile,
    SourceSymbol,
    TraceEvent,
    XmlRecord,
)
from odoo_ai.storage.runtime_repository import (
    UnsafeTraceAttributesError,
    create_capability_snapshot,
    create_instance_profile,
    create_trace_event,
    get_instance_profile,
    get_latest_capability_snapshot,
    get_latest_instance_profile,
    list_trace_events,
    record_source_capability,
)
from odoo_ai.storage.source_repository import (
    SourceFileUpsert,
    SourceSymbolValues,
    XmlRecordValues,
    delete_stale_source_files,
    find_source_symbols,
    find_xml_records,
    finish_scan,
    mark_stale_source_files,
    open_scan,
    replace_file_derivatives,
    upsert_source_file,
)

__all__ = [
    "Base",
    "CapabilitySnapshot",
    "DatabaseConfigurationError",
    "DatabaseSettings",
    "InstanceProfile",
    "ScanRun",
    "SourceFile",
    "SourceFileUpsert",
    "SourceSymbol",
    "SourceSymbolValues",
    "TraceEvent",
    "UnsafeTraceAttributesError",
    "XmlRecord",
    "XmlRecordValues",
    "create_capability_snapshot",
    "create_database_engine",
    "create_instance_profile",
    "create_session_factory",
    "create_trace_event",
    "delete_stale_source_files",
    "find_source_symbols",
    "find_xml_records",
    "finish_scan",
    "get_instance_profile",
    "get_latest_capability_snapshot",
    "get_latest_instance_profile",
    "list_trace_events",
    "record_source_capability",
    "mark_stale_source_files",
    "open_scan",
    "replace_file_derivatives",
    "session_scope",
    "upsert_source_file",
]
