"""M7 structured diagnostics matrix and bounded runtime probes."""

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
from odoo_ai.runtime.configuration import (
    RuntimeConfigurationError,
    RuntimeConfigurationService,
)
from odoo_ai.runtime.status import (
    AdminStatus,
    ComponentState,
    ReasoningComponentStatus,
    inspect_admin_status,
)
from odoo_ai.security import ActionAuthorityCodec, ActionAuthorityError
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


_PRESENTATION: Mapping[str, _Presentation] = {
    "service_reachable": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Assistant Service endpoint is reachable.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "machine_auth_validated": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Machine authentication was validated for this request.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "database_available": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Assistant PostgreSQL storage is available.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "database_unavailable": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "Assistant PostgreSQL storage is unavailable.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Review the host-owned Assistant database setup and retry.",
    ),
    "migrations_at_head": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Assistant database migrations are at the expected revision.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "migrations_revision_mismatch": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "Assistant database migration revision does not match this service version.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Run the controlled Assistant upgrade procedure before using the service.",
    ),
    "configuration_valid": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Effective M7 runtime configuration is valid.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "configuration_invalid": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "Effective M7 runtime configuration is invalid against current host boundaries.",
        DiagnosticRemediationKind.SETTINGS,
        "Review AI Assistant Settings or restore the host-owned boundary that made the last revision valid.",
    ),
    "instance_available": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "An authenticated Odoo instance profile is available.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "instance_unknown": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "No current Odoo instance profile is available.",
        DiagnosticRemediationKind.RETRY,
        "Open or use the assistant from Odoo, then refresh diagnostics.",
    ),
    "source_operational": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Source index capability is operational.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "source_not_found": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "No usable source tree was found inside the authorized roots.",
        DiagnosticRemediationKind.SETTINGS,
        "Review the selected source roots and the setup-authorized envelope.",
    ),
    "source_no_permission": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The Assistant cannot read the configured source roots.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Correct host filesystem permissions without granting Odoo additional privileges.",
    ),
    "source_error": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "Source indexing reported an operational error.",
        DiagnosticRemediationKind.RESCAN,
        "Retry the bounded source scan after reviewing configuration.",
    ),
    "source_unknown": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Source capability has not been established yet.",
        DiagnosticRemediationKind.RESCAN,
        "Run the existing bounded source scan and refresh diagnostics.",
    ),
    "source_scan_succeeded": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "The latest source scan completed successfully.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "source_scan_running": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "A source scan is currently in progress.",
        DiagnosticRemediationKind.RETRY,
        "Refresh diagnostics after the current scan completes.",
    ),
    "source_scan_failed": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The latest source scan failed.",
        DiagnosticRemediationKind.RESCAN,
        "Review source configuration and run the bounded scan again.",
    ),
    "source_scan_unknown": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "No completed source scan is available yet.",
        DiagnosticRemediationKind.RESCAN,
        "Run the existing bounded source scan.",
    ),
    "logs_operational": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "The selected log provider is operational.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "logs_not_found": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "No authorized log source is currently available.",
        DiagnosticRemediationKind.SETTINGS,
        "Select an authorized provider or review host log setup.",
    ),
    "logs_no_permission": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The Assistant cannot read the authorized log source.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Correct host log permissions without granting Odoo host privileges.",
    ),
    "logs_error": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The selected log provider reported an operational error.",
        DiagnosticRemediationKind.RETRY,
        "Retry the bounded log diagnostic after reviewing provider setup.",
    ),
    "logs_unknown": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Log capability has not been established yet.",
        DiagnosticRemediationKind.RETRY,
        "Run the existing bounded log test and refresh diagnostics.",
    ),
    "knowledge_index_available": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "The Assistant knowledge index is available and contains current documents.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "knowledge_index_empty": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "The knowledge index is available but has no current documents.",
        DiagnosticRemediationKind.REINDEX,
        "Use the bounded knowledge maintenance operation when available.",
    ),
    "knowledge_index_unavailable": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The knowledge index could not be inspected safely.",
        DiagnosticRemediationKind.RETRY,
        "Verify Assistant storage and migrations, then refresh diagnostics.",
    ),
    "reasoning_operational": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Codex App Server is operational.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "reasoning_not_configured": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Codex runtime is not configured.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Configure the host-owned Codex executable and runtime home.",
    ),
    "reasoning_runtime_missing": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The configured Codex runtime is not available to the Assistant process.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Repair the host runtime installation or executable selection.",
    ),
    "reasoning_auth_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Codex runtime authentication is unavailable.",
        DiagnosticRemediationKind.AUTHENTICATE_RUNTIME,
        "Authenticate Codex as the operating-system user that runs the Assistant Service.",
    ),
    "reasoning_protocol_incompatible": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The configured Codex runtime protocol is incompatible with this Assistant version.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Install a compatible Codex runtime version and retry the probe.",
    ),
    "reasoning_error": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "The reasoning runtime could not be validated.",
        DiagnosticRemediationKind.RETRY,
        "Retry the runtime probe after reviewing host setup.",
    ),
    "action_authority_available": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "M6 ACTION commit authority is configured.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "action_authority_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "M6 ACTION commit authority is unavailable.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Provision the host-owned ACTION authority secret using the controlled setup boundary.",
    ),
    "workflow_ready": _Presentation(
        DiagnosticState.OK,
        DiagnosticSeverity.INFO,
        "Workflow prerequisites are currently available.",
        DiagnosticRemediationKind.NONE,
        "No action required.",
    ),
    "workflow_reasoning_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Workflow is blocked by the reasoning runtime.",
        DiagnosticRemediationKind.RETRY,
        "Resolve the Codex diagnostic first, then retry.",
    ),
    "workflow_knowledge_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "Workflow is waiting for instance or knowledge state.",
        DiagnosticRemediationKind.REINDEX,
        "Refresh instance state and rebuild knowledge when the bounded maintenance action is available.",
    ),
    "workflow_source_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "EXPLAIN is degraded because source evidence is unavailable.",
        DiagnosticRemediationKind.RESCAN,
        "Resolve the source diagnostic and run the bounded source scan.",
    ),
    "workflow_action_authority_unavailable": _Presentation(
        DiagnosticState.DEGRADED,
        DiagnosticSeverity.WARNING,
        "ACTION cannot commit because its host authority is unavailable.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Provision ACTION authority through setup; do not expose the secret to Odoo.",
    ),
    "assistant_runtime_unavailable": _Presentation(
        DiagnosticState.ERROR,
        DiagnosticSeverity.ERROR,
        "Workflow is blocked by Assistant storage, migrations, or configuration.",
        DiagnosticRemediationKind.SETUP_REQUIRED,
        "Resolve the blocking Assistant component before retrying workflows.",
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
    """Compose existing probes into one structured, fail-closed admin matrix."""

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
        authority_ready = await asyncio.to_thread(_action_authority_ready)
        return build_admin_diagnostics_matrix(
            status=status,
            configuration=configuration,
            source_status=source_status,
            knowledge_probe=knowledge_probe,
            action_authority_ready=authority_ready,
        )

    async def _reasoning_status(self) -> ReasoningComponentStatus:
        try:
            if self._reasoning_probe is None:
                self._reasoning_probe = CachedCodexReasoningStatus.from_env()
            return await self._reasoning_probe.inspect()
        except (OSError, RuntimeError, ValueError):
            return ReasoningComponentStatus(
                state=ComponentState.PENDING,
                detail="error",
            )


def build_admin_diagnostics_matrix(
    *,
    status: AdminStatus,
    configuration: AdminConfigurationResponse | None,
    source_status: SourceStatusDiagnostics | None,
    knowledge_probe: KnowledgeProbe,
    action_authority_ready: bool,
) -> AdminDiagnosticsMatrix:
    """Map only allowlisted backend states to trusted diagnostic reason codes."""

    checked_at = status.checked_at
    revision = configuration.revision if configuration is not None else 0
    entries: list[AdminDiagnosticEntry] = [
        _entry("service.endpoint", DiagnosticScope.COMPONENT, "service_reachable", checked_at, revision),
        _entry(
            "service.machine_auth",
            DiagnosticScope.COMPONENT,
            "machine_auth_validated",
            checked_at,
            revision,
        ),
        _entry(
            "assistant.database",
            DiagnosticScope.COMPONENT,
            (
                "database_available"
                if status.components.assistant_database.state is ComponentState.OK
                else "database_unavailable"
            ),
            checked_at,
            revision,
        ),
        _entry(
            "assistant.migrations",
            DiagnosticScope.COMPONENT,
            _migration_reason(status),
            checked_at,
            revision,
        ),
        _entry(
            "assistant.configuration",
            DiagnosticScope.COMPONENT,
            (
                "configuration_valid"
                if status.components.configuration.state is ComponentState.OK
                else "configuration_invalid"
            ),
            checked_at,
            revision,
        ),
        _entry(
            "instance.profile",
            DiagnosticScope.COMPONENT,
            "instance_available" if status.instance is not None else "instance_unknown",
            checked_at,
            revision,
        ),
        _entry(
            "source.index",
            DiagnosticScope.COMPONENT,
            _source_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "source.selected_roots"),
        ),
        _entry(
            "source.scan",
            DiagnosticScope.COMPONENT,
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
            DiagnosticScope.COMPONENT,
            _logs_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "logs.provider"),
        ),
        _entry(
            "knowledge.index",
            DiagnosticScope.COMPONENT,
            _knowledge_reason(knowledge_probe),
            checked_at,
            revision,
        ),
        _entry(
            "reasoning.codex",
            DiagnosticScope.COMPONENT,
            _reasoning_reason(status),
            checked_at,
            revision,
            provenance=_provenance(configuration, "reasoning.model"),
        ),
        _entry(
            "action.authority",
            DiagnosticScope.COMPONENT,
            "action_authority_available" if action_authority_ready else "action_authority_unavailable",
            checked_at,
            revision,
        ),
        _entry(
            "workflow.explain",
            DiagnosticScope.WORKFLOW,
            _explain_reason(status),
            checked_at,
            revision,
        ),
        _entry(
            "workflow.query",
            DiagnosticScope.WORKFLOW,
            _workflow_reason(status.workflow_capabilities.query.detail),
            checked_at,
            revision,
        ),
        _entry(
            "workflow.how_to",
            DiagnosticScope.WORKFLOW,
            _workflow_reason(status.workflow_capabilities.how_to.detail),
            checked_at,
            revision,
        ),
        _entry(
            "workflow.action",
            DiagnosticScope.WORKFLOW,
            _workflow_reason(status.workflow_capabilities.action.detail),
            checked_at,
            revision,
        ),
    ]
    readiness = _matrix_readiness(status, entries)
    return AdminDiagnosticsMatrix(
        readiness=readiness,
        checked_at=checked_at,
        config_revision=revision,
        entries=tuple(entries),
    )


def _entry(
    key: str,
    scope: DiagnosticScope,
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
        scope=scope,
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
    component = status.components.source
    mapping = {
        "operational": "source_operational",
        "not_found": "source_not_found",
        "no_permission": "source_no_permission",
        "error": "source_error",
        "unknown": "source_unknown",
    }
    return mapping.get(component.detail, "status_unrecognized")


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
    component = status.components.logs
    mapping = {
        "operational": "logs_operational",
        "not_found": "logs_not_found",
        "no_permission": "logs_no_permission",
        "error": "logs_error",
        "unknown": "logs_unknown",
    }
    return mapping.get(component.detail, "status_unrecognized")


def _knowledge_reason(probe: KnowledgeProbe) -> str:
    return {
        "available": "knowledge_index_available",
        "empty": "knowledge_index_empty",
        "instance_unknown": "instance_unknown",
        "unavailable": "knowledge_index_unavailable",
    }[probe]


def _reasoning_reason(status: AdminStatus) -> str:
    detail = status.components.reasoning_engine.detail
    return {
        "operational": "reasoning_operational",
        "not_configured": "reasoning_not_configured",
        "runtime_missing": "reasoning_runtime_missing",
        "auth_unavailable": "reasoning_auth_unavailable",
        "protocol_incompatible": "reasoning_protocol_incompatible",
        "error": "reasoning_error",
        "unknown": "reasoning_error",
    }.get(detail, "status_unrecognized")


def _explain_reason(status: AdminStatus) -> str:
    if (
        status.components.assistant_database.state is not ComponentState.OK
        or status.components.migrations.state is not ComponentState.OK
        or status.components.configuration.state is not ComponentState.OK
    ):
        return "assistant_runtime_unavailable"
    if status.components.reasoning_engine.state is not ComponentState.OK:
        return "workflow_reasoning_unavailable"
    if status.components.source.state is not ComponentState.OK:
        return "workflow_source_unavailable"
    return "workflow_ready"


def _workflow_reason(detail: str) -> str:
    return {
        "validated_per_turn": "workflow_ready",
        "reasoning_unavailable": "workflow_reasoning_unavailable",
        "knowledge_unavailable": "workflow_knowledge_unavailable",
        "instance_unknown": "workflow_knowledge_unavailable",
        "action_authority_unavailable": "workflow_action_authority_unavailable",
        "assistant_runtime_unavailable": "assistant_runtime_unavailable",
    }.get(detail, "status_unrecognized")


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


def _action_authority_ready() -> bool:
    try:
        ActionAuthorityCodec.from_env()
    except ActionAuthorityError:
        return False
    return True
