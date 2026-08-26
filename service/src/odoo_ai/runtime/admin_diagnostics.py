"""Structured diagnostics for residual service components."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.adapters import CachedCodexReasoningStatus, RuntimeDiagnosticsService
from odoo_ai.contracts.admin_configuration import AdminConfigurationResponse
from odoo_ai.contracts.admin_diagnostics import (
    AdminDiagnosticEntry,
    AdminDiagnosticsMatrix,
    DiagnosticReasonCode,
    DiagnosticRemediationKind,
    DiagnosticScope,
    DiagnosticSeverity,
    DiagnosticState,
)
from odoo_ai.contracts.configuration import ConfigProvenance
from odoo_ai.contracts.diagnostics import SourceStatusDiagnostics
from odoo_ai.runtime.configuration import RuntimeConfigurationError, RuntimeConfigurationService
from odoo_ai.runtime.status import (
    AdminStatus,
    ComponentState,
    ReasoningComponentStatus,
    inspect_admin_status,
)
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    KnowledgeDocument,
    create_database_engine,
    create_session_factory,
    get_latest_instance_profile,
    session_scope,
)

KnowledgeProbe = Literal["available", "empty", "instance_unknown", "unavailable"]


@dataclass(frozen=True, slots=True)
class _Presentation:
    state: DiagnosticState
    severity: DiagnosticSeverity
    summary: str
    remediation_kind: DiagnosticRemediationKind
    remediation_text: str


def _ok(summary: str) -> _Presentation:
    return _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        summary,
        DiagnosticRemediationKind.NONE,
        "No action required.",
    )


def _degraded(
    summary: str,
    remediation_kind: DiagnosticRemediationKind,
    remediation_text: str,
) -> _Presentation:
    return _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        summary,
        remediation_kind,
        remediation_text,
    )


def _error(
    summary: str,
    remediation_kind: DiagnosticRemediationKind,
    remediation_text: str,
) -> _Presentation:
    return _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        summary,
        remediation_kind,
        remediation_text,
    )


_PRESENTATION: Mapping[str, _Presentation] = {
    "service_reachable": _ok("Assistant Service endpoint is reachable."),
    "machine_auth_validated": _ok("Machine authentication was validated for this request."),
    "database_available": _ok("Assistant PostgreSQL storage is available."),
    "database_unavailable": _error(
        "Assistant PostgreSQL storage is unavailable.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Review the host-owned Assistant database setup and retry.",
    ),
    "migrations_at_head": _ok("Assistant database migrations are at the expected revision."),
    "migrations_revision_mismatch": _error(
        "Assistant database migration revision does not match this service version.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Run the controlled Assistant upgrade procedure before using the service.",
    ),
    "configuration_valid": _ok("Effective runtime configuration is valid."),
    "configuration_invalid": _error(
        "Effective runtime configuration is invalid against current host boundaries.",
        DiagnosticRemediationKind.SETTINGS,
        "Review AI Assistant Settings or restore the host-owned boundary that made the last revision valid.",
    ),
    "instance_available": _ok("An authenticated Odoo instance profile is available."),
    "instance_unknown": _degraded(
        "No current Odoo instance profile is available.",
        DiagnosticRemediationKind.RETRY,
        "Open or use the assistant from Odoo, then refresh diagnostics.",
    ),
    "source_operational": _ok("Source index capability is operational."),
    "source_not_found": _degraded(
        "No usable source tree was found inside the authorized roots.",
        DiagnosticRemediationKind.SETTINGS,
        "Review the selected source roots and the setup-authorized envelope.",
    ),
    "source_no_permission": _error(
        "The Assistant cannot read the configured source roots.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Correct host filesystem permissions without granting Odoo additional privileges.",
    ),
    "source_error": _error(
        "Source indexing reported an operational error.",
        DiagnosticRemediationKind.RESCAN,
        "Retry the bounded source scan after reviewing configuration.",
    ),
    "source_unknown": _degraded(
        "Source capability has not been established yet.",
        DiagnosticRemediationKind.RESCAN,
        "Run the existing bounded source scan and refresh diagnostics.",
    ),
    "source_scan_succeeded": _ok("The latest source scan completed successfully."),
    "source_scan_running": _degraded(
        "A source scan is currently in progress.",
        DiagnosticRemediationKind.RETRY,
        "Refresh diagnostics after the current scan completes.",
    ),
    "source_scan_failed": _error(
        "The latest source scan failed.",
        DiagnosticRemediationKind.RESCAN,
        "Review source configuration and run the bounded scan again.",
    ),
    "source_scan_unknown": _degraded(
        "No completed source scan is available yet.",
        DiagnosticRemediationKind.RESCAN,
        "Run the existing bounded source scan.",
    ),
    "logs_operational": _ok("The selected log provider is operational."),
    "logs_not_found": _degraded(
        "No authorized log source is currently available.",
        DiagnosticRemediationKind.SETTINGS,
        "Select an authorized provider or review host log setup.",
    ),
    "logs_no_permission": _error(
        "The Assistant cannot read the authorized log source.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Correct host log permissions without granting Odoo host privileges.",
    ),
    "logs_error": _error(
        "The selected log provider reported an operational error.",
        DiagnosticRemediationKind.RETRY,
        "Retry the bounded log diagnostic after reviewing provider setup.",
    ),
    "logs_unknown": _degraded(
        "Log capability has not been established yet.",
        DiagnosticRemediationKind.RETRY,
        "Run the existing bounded log test and refresh diagnostics.",
    ),
    "knowledge_index_available": _ok(
        "The Assistant knowledge index is available and contains current documents."
    ),
    "knowledge_index_empty": _degraded(
        "The knowledge index is available but has no current documents.",
        DiagnosticRemediationKind.REINDEX,
        "Use the bounded knowledge maintenance operation when available.",
    ),
    "knowledge_index_unavailable": _error(
        "The knowledge index could not be inspected safely.",
        DiagnosticRemediationKind.RETRY,
        "Verify Assistant storage and migrations, then refresh diagnostics.",
    ),
    "reasoning_operational": _ok("Codex App Server is operational."),
    "reasoning_not_configured": _degraded(
        "Codex runtime is not configured.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Configure the host-owned Codex executable and runtime home.",
    ),
    "reasoning_runtime_missing": _error(
        "The configured Codex runtime is not available to the Assistant process.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Repair the host runtime installation or executable selection.",
    ),
    "reasoning_auth_unavailable": _degraded(
        "Codex runtime authentication is unavailable.",
        DiagnosticRemediationKind.AUTHENTICATE_RUNTIME,
        "Authenticate Codex as the operating-system user that runs the Assistant Service.",
    ),
    "reasoning_protocol_incompatible": _error(
        "The configured Codex runtime protocol is incompatible with this Assistant version.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Install a compatible Codex runtime version and retry the probe.",
    ),
    "reasoning_error": _error(
        "The reasoning runtime could not be validated.",
        DiagnosticRemediationKind.RETRY,
        "Retry the runtime probe after reviewing host setup.",
    ),
    "assistant_runtime_unavailable": _error(
        "Assistant runtime is blocked by storage, migrations, or configuration.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Resolve the blocking Assistant component before retrying.",
    ),
    "status_unrecognized": _Presentation(
        DiagnosticState.UNKNOWN,
        DiagnosticSeverity.WARNING,
        "A backend status was not recognized by this diagnostic contract.",
        DiagnosticRemediationKind.RETRY,
        "Refresh after upgrading matching Assistant and addon versions.",
    ),
}


class RuntimeAdminDiagnosticsService:
    """Compose existing component probes into one structured, fail-closed matrix."""

    def __init__(self) -> None:
        self._reasoning_probe: CachedCodexReasoningStatus | None = None

    @classmethod
    def from_env(cls) -> RuntimeAdminDiagnosticsService:
        return cls()

    async def inspect(self) -> AdminDiagnosticsMatrix:
        reasoning = await self._reasoning_status()
        status = await asyncio.to_thread(inspect_admin_status, reasoning=reasoning)
        configuration = await asyncio.to_thread(_configuration_snapshot)
        source_status = await _source_status()
        knowledge_probe = await asyncio.to_thread(_knowledge_index_probe)
        return build_admin_diagnostics_matrix(
            status=status,
            configuration=configuration,
            source_status=source_status,
            knowledge_probe=knowledge_probe,
        )

    async def _reasoning_status(self) -> ReasoningComponentStatus:
        try:
            if self._reasoning_probe is None:
                self._reasoning_probe = CachedCodexReasoningStatus.from_env()
            return await self._reasoning_probe.inspect()
        except (OSError, RuntimeError, ValueError):
            return ReasoningComponentStatus(state=ComponentState.PENDING, detail="error")


def build_admin_diagnostics_matrix(
    *,
    status: AdminStatus,
    configuration: AdminConfigurationResponse | None,
    source_status: SourceStatusDiagnostics | None,
    knowledge_probe: KnowledgeProbe,
) -> AdminDiagnosticsMatrix:
    """Map only allowlisted component states to trusted diagnostic reason codes."""

    checked_at = status.checked_at
    revision = configuration.revision if configuration is not None else 0
    entries = [
        _entry("service.endpoint", "service_reachable", checked_at, revision),
        _entry("service.machine_auth", "machine_auth_validated", checked_at, revision),
        _entry(
            "assistant.database",
            "database_available"
            if status.components.assistant_database.state is ComponentState.OK
            else "database_unavailable",
            checked_at,
            revision,
        ),
        _entry("assistant.migrations", _migration_reason(status), checked_at, revision),
        _entry(
            "assistant.configuration",
            "configuration_valid"
            if status.components.configuration.state is ComponentState.OK
            else "configuration_invalid",
            checked_at,
            revision,
        ),
        _entry(
            "instance.profile",
            "instance_available" if status.instance is not None else "instance_unknown",
            checked_at,
            revision,
        ),
        _entry(
            "source.index",
            _source_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "source.selected_roots"),
        ),
        _entry(
            "source.scan",
            _source_scan_reason(source_status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "source.selected_roots"),
            evidence_ref=(
                f"source-scan:{source_status.scan_id}"
                if source_status is not None and source_status.scan_id is not None
                else None
            ),
        ),
        _entry(
            "logs.provider",
            _logs_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "logs.provider"),
        ),
        _entry("knowledge.index", _knowledge_reason(knowledge_probe), checked_at, revision),
        _entry(
            "reasoning.codex",
            _reasoning_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "reasoning.model"),
        ),
    ]
    return AdminDiagnosticsMatrix(
        readiness=_matrix_readiness(status, entries),
        checked_at=checked_at,
        config_revision=revision,
        entries=tuple(entries),
    )


def _entry(
    key: str,
    reason: str,
    checked_at: datetime,
    revision: int,
    *,
    provenance: ConfigProvenance | None = None,
    evidence_ref: str | None = None,
) -> AdminDiagnosticEntry:
    presentation = _PRESENTATION.get(reason, _PRESENTATION["status_unrecognized"])
    safe_reason = reason if reason in _PRESENTATION else "status_unrecognized"
    return AdminDiagnosticEntry(
        key=key,
        scope=DiagnosticScope.COMPONENT,
        state=presentation.state,
        severity=presentation.severity,
        reason_code=cast(DiagnosticReasonCode, safe_reason),
        summary=presentation.summary,
        checked_at=checked_at,
        config_revision=revision,
        provenance=provenance,
        remediation_kind=presentation.remediation_kind,
        remediation_text=presentation.remediation_text,
        evidence_ref=evidence_ref,
    )


def _migration_reason(status: AdminStatus) -> str:
    component = status.components.migrations
    if component.state is ComponentState.OK and component.detail == "at_head":
        return "migrations_at_head"
    if component.detail == "revision_mismatch":
        return "migrations_revision_mismatch"
    return "status_unrecognized"


def _source_reason(status: AdminStatus) -> str:
    if status.components.configuration.state is not ComponentState.OK:
        return "assistant_runtime_unavailable"
    return {
        "operational": "source_operational",
        "not_found": "source_not_found",
        "no_permission": "source_no_permission",
        "error": "source_error",
        "unknown": "source_unknown",
    }.get(status.components.source.detail, "status_unrecognized")


def _source_scan_reason(source_status: SourceStatusDiagnostics | None) -> str:
    if source_status is None:
        return "source_scan_unknown"
    return {
        "succeeded": "source_scan_succeeded",
        "running": "source_scan_running",
        "failed": "source_scan_failed",
        "unknown": "source_scan_unknown",
    }.get(source_status.scan_status, "status_unrecognized")


def _logs_reason(status: AdminStatus) -> str:
    if status.components.configuration.state is not ComponentState.OK:
        return "assistant_runtime_unavailable"
    return {
        "operational": "logs_operational",
        "not_found": "logs_not_found",
        "no_permission": "logs_no_permission",
        "error": "logs_error",
        "unknown": "logs_unknown",
    }.get(status.components.logs.detail, "status_unrecognized")


def _knowledge_reason(probe: KnowledgeProbe) -> str:
    return {
        "available": "knowledge_index_available",
        "empty": "knowledge_index_empty",
        "instance_unknown": "instance_unknown",
        "unavailable": "knowledge_index_unavailable",
    }[probe]


def _reasoning_reason(status: AdminStatus) -> str:
    return {
        "operational": "reasoning_operational",
        "not_configured": "reasoning_not_configured",
        "runtime_missing": "reasoning_runtime_missing",
        "auth_unavailable": "reasoning_auth_unavailable",
        "protocol_incompatible": "reasoning_protocol_incompatible",
        "error": "reasoning_error",
        "unknown": "reasoning_error",
    }.get(status.components.reasoning_engine.detail, "status_unrecognized")


def _provenance(
    configuration: AdminConfigurationResponse | None,
    key: str,
) -> ConfigProvenance | None:
    if configuration is None:
        return None
    for value in configuration.snapshot.values:
        if value.key == key:
            return value.provenance
    return None


def _matrix_readiness(
    status: AdminStatus,
    entries: list[AdminDiagnosticEntry],
) -> Literal["FULLY_READY", "DEGRADED", "ERROR"]:
    if status.readiness == "ERROR" or any(
        item.severity is DiagnosticSeverity.ERROR for item in entries
    ):
        return "ERROR"
    if status.readiness == "DEGRADED" or any(
        item.state in {DiagnosticState.DEGRADED, DiagnosticState.UNKNOWN}
        for item in entries
    ):
        return "DEGRADED"
    return "FULLY_READY"


def _configuration_snapshot() -> AdminConfigurationResponse | None:
    try:
        return RuntimeConfigurationService.from_env().snapshot()
    except (RuntimeConfigurationError, DatabaseConfigurationError, OSError, ValueError):
        return None


async def _source_status() -> SourceStatusDiagnostics | None:
    try:
        return await RuntimeDiagnosticsService.from_env().source_status()
    except Exception:  # noqa: BLE001 - converted to a fixed unknown diagnostic state
        return None


def _knowledge_index_probe() -> KnowledgeProbe:
    engine = None
    try:
        settings = DatabaseSettings.from_env()
        engine = create_database_engine(settings)
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                return "instance_unknown"
            count = session.scalar(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.instance_profile_id == profile.id,
                    KnowledgeDocument.status == "current",
                )
            )
            return "available" if count is not None and count > 0 else "empty"
    except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
        return "unavailable"
    finally:
        if engine is not None:
            engine.dispose()
