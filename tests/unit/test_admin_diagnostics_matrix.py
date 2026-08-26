"""Unit coverage for the residual structured diagnostics matrix."""

from datetime import UTC, datetime

import pytest

from odoo_ai.contracts.admin_diagnostics import DiagnosticRemediationKind, DiagnosticState
from odoo_ai.contracts.diagnostics import SourceStatusDiagnostics
from odoo_ai.runtime.admin_diagnostics import build_admin_diagnostics_matrix
from odoo_ai.runtime.status import (
    AdminStatus,
    ComponentState,
    ComponentStatus,
    InstanceStatus,
    MigrationStatus,
    ReasoningComponentStatus,
    RuntimeComponents,
)


def _status(*, configuration: ComponentStatus | None = None, source: ComponentStatus | None = None, logs: ComponentStatus | None = None, reasoning: ReasoningComponentStatus | None = None) -> AdminStatus:
    ok = ComponentStatus(state=ComponentState.OK, detail="available")
    return AdminStatus(
        readiness="FULLY_READY",
        checked_at=datetime(2026, 8, 23, 21, 0, tzinfo=UTC),
        components=RuntimeComponents(
            runtime=ComponentStatus(state=ComponentState.OK, detail="running"),
            assistant_database=ok,
            migrations=MigrationStatus(state=ComponentState.OK, detail="at_head", current_revision="0011_m7_03_runtime_configuration", expected_revision="0011_m7_03_runtime_configuration"),
            configuration=configuration or ComponentStatus(state=ComponentState.OK, detail="valid"),
            source=source or ComponentStatus(state=ComponentState.OK, detail="operational"),
            logs=logs or ComponentStatus(state=ComponentState.OK, detail="operational"),
            reasoning_engine=reasoning or ReasoningComponentStatus(state=ComponentState.OK, detail="operational", protocol="app-server-jsonl-v2", runtime_version="0.149.0", model="test-model"),
        ),
        pending_capabilities=(),
        instance=InstanceStatus(instance_id="odoo:test", fingerprint="sha256:test", capabilities={}),
    )


def _entries(matrix):
    return {entry.key: entry for entry in matrix.entries}


def _matrix(status: AdminStatus, *, source_scan: str = "succeeded", knowledge_probe: str = "available"):
    return build_admin_diagnostics_matrix(status=status, configuration=None, source_status=SourceStatusDiagnostics(state="DETECTED", scan_status=source_scan), knowledge_probe=knowledge_probe)


def test_healthy_matrix_covers_only_current_components() -> None:
    matrix = _matrix(_status())
    entries = _entries(matrix)
    assert matrix.schema_version == 1
    assert matrix.readiness == "FULLY_READY"
    assert set(entries) == {"service.endpoint", "service.machine_auth", "assistant.database", "assistant.migrations", "assistant.configuration", "instance.profile", "source.index", "source.scan", "logs.provider", "knowledge.index", "reasoning.codex"}
    assert all(entry.state is DiagnosticState.OK for entry in matrix.entries)


def test_invalid_configuration_is_distinct_from_provider_unavailable() -> None:
    matrix = _matrix(_status(configuration=ComponentStatus(state=ComponentState.ERROR, detail="invalid"), logs=ComponentStatus(state=ComponentState.PENDING, detail="unknown")))
    entries = _entries(matrix)
    assert entries["assistant.configuration"].reason_code == "configuration_invalid"
    assert entries["logs.provider"].reason_code == "assistant_runtime_unavailable"
    assert matrix.readiness == "ERROR"


@pytest.mark.parametrize(("detail", "state", "reason", "remediation"), [("not_found", ComponentState.PENDING, "source_not_found", DiagnosticRemediationKind.SETTINGS), ("no_permission", ComponentState.ERROR, "source_no_permission", DiagnosticRemediationKind.SETUP_REQUIRED), ("error", ComponentState.ERROR, "source_error", DiagnosticRemediationKind.RESCAN)])
def test_source_failures_have_stable_reason_and_remediation(detail: str, state: ComponentState, reason: str, remediation: DiagnosticRemediationKind) -> None:
    entry = _entries(_matrix(_status(source=ComponentStatus(state=state, detail=detail))))["source.index"]
    assert entry.reason_code == reason
    assert entry.remediation_kind is remediation


@pytest.mark.parametrize(("detail", "state", "reason", "remediation"), [("not_found", ComponentState.PENDING, "logs_not_found", DiagnosticRemediationKind.SETTINGS), ("no_permission", ComponentState.ERROR, "logs_no_permission", DiagnosticRemediationKind.SETUP_REQUIRED), ("error", ComponentState.ERROR, "logs_error", DiagnosticRemediationKind.RETRY)])
def test_log_failures_have_stable_reason_and_remediation(detail: str, state: ComponentState, reason: str, remediation: DiagnosticRemediationKind) -> None:
    entry = _entries(_matrix(_status(logs=ComponentStatus(state=state, detail=detail))))["logs.provider"]
    assert entry.reason_code == reason
    assert entry.remediation_kind is remediation


@pytest.mark.parametrize(("detail", "state", "reason", "remediation"), [("runtime_missing", ComponentState.PENDING, "reasoning_runtime_missing", DiagnosticRemediationKind.SETUP_REQUIRED), ("auth_unavailable", ComponentState.PENDING, "reasoning_auth_unavailable", DiagnosticRemediationKind.AUTHENTICATE_RUNTIME), ("protocol_incompatible", ComponentState.PENDING, "reasoning_protocol_incompatible", DiagnosticRemediationKind.SETUP_REQUIRED)])
def test_codex_failures_have_stable_reason_and_remediation(detail: str, state: ComponentState, reason: str, remediation: DiagnosticRemediationKind) -> None:
    entry = _entries(_matrix(_status(reasoning=ReasoningComponentStatus(state=state, detail=detail))))["reasoning.codex"]
    assert entry.reason_code == reason
    assert entry.remediation_kind is remediation


def test_unknown_backend_detail_becomes_unrecognized_not_free_text() -> None:
    matrix = _matrix(_status(logs=ComponentStatus(state=ComponentState.ERROR, detail="backend-secret-canary")))
    assert _entries(matrix)["logs.provider"].reason_code == "status_unrecognized"
    assert "backend-secret-canary" not in matrix.model_dump_json()


@pytest.mark.parametrize(("probe", "reason", "readiness"), [("empty", "knowledge_index_empty", "DEGRADED"), ("unavailable", "knowledge_index_unavailable", "ERROR")])
def test_knowledge_states_are_structured(probe: str, reason: str, readiness: str) -> None:
    matrix = _matrix(_status(), knowledge_probe=probe)
    assert matrix.readiness == readiness
    assert _entries(matrix)["knowledge.index"].reason_code == reason


def test_failed_source_scan_is_separate_from_source_provider_state() -> None:
    matrix = _matrix(_status(), source_scan="failed")
    entries = _entries(matrix)
    assert entries["source.index"].reason_code == "source_operational"
    assert entries["source.scan"].reason_code == "source_scan_failed"
    assert entries["source.scan"].remediation_kind is DiagnosticRemediationKind.RESCAN
    assert matrix.readiness == "ERROR"
