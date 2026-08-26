"""Versioned, bounded M7 administrator diagnostics contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.configuration import ConfigProvenance

DIAGNOSTIC_SCHEMA_VERSION = 1


class DiagnosticScope(StrEnum):
    COMPONENT = "component"


class DiagnosticState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
    UNKNOWN = "unknown"


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticRemediationKind(StrEnum):
    SETTINGS = "settings"
    SETUP_REQUIRED = "setup_required"
    RETRY = "retry"
    RESCAN = "rescan"
    REINDEX = "reindex"
    AUTHENTICATE_RUNTIME = "authenticate_runtime"
    NONE = "none"


DiagnosticReasonCode = Literal[
    "service_reachable",
    "machine_auth_validated",
    "database_available",
    "database_unavailable",
    "migrations_at_head",
    "migrations_revision_mismatch",
    "configuration_valid",
    "configuration_invalid",
    "instance_available",
    "instance_unknown",
    "source_operational",
    "source_not_found",
    "source_no_permission",
    "source_error",
    "source_unknown",
    "source_scan_succeeded",
    "source_scan_running",
    "source_scan_failed",
    "source_scan_unknown",
    "logs_operational",
    "logs_not_found",
    "logs_no_permission",
    "logs_error",
    "logs_unknown",
    "knowledge_index_available",
    "knowledge_index_empty",
    "knowledge_index_unavailable",
    "reasoning_operational",
    "reasoning_not_configured",
    "reasoning_runtime_missing",
    "reasoning_auth_unavailable",
    "reasoning_protocol_incompatible",
    "reasoning_error",
    "assistant_runtime_unavailable",
    "status_unrecognized",
]


class AdminDiagnosticEntry(BaseModel):
    """One trusted, bounded diagnostic fact and its fixed remediation category."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    scope: DiagnosticScope
    state: DiagnosticState
    severity: DiagnosticSeverity
    reason_code: DiagnosticReasonCode
    summary: str = Field(min_length=1, max_length=240)
    checked_at: datetime
    config_revision: int = Field(ge=0)
    provenance: ConfigProvenance | None = None
    remediation_kind: DiagnosticRemediationKind
    remediation_text: str = Field(min_length=1, max_length=240)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=128)


class AdminDiagnosticsMatrix(BaseModel):
    """Complete operational view consumed only by authenticated administrators."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = DIAGNOSTIC_SCHEMA_VERSION
    readiness: Literal["FULLY_READY", "DEGRADED", "ERROR"]
    checked_at: datetime
    config_revision: int = Field(ge=0)
    entries: tuple[AdminDiagnosticEntry, ...] = Field(max_length=32)
