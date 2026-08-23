"""Unit coverage for the M7 structured diagnostics matrix."""

from datetime import UTC, datetime

from odoo_ai.contracts.admin_diagnostics import (
    DiagnosticRemediationKind,
    DiagnosticState,
)
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
    WorkflowCapabilities,
)


def _status(
    *,
    configuration: ComponentStatus | None = None,
    source: ComponentStatus | None = None,
    logs: ComponentStatus | None = None,
    reasoning: ReasoningComponentStatus | None = None,
    action_detail: str = "validated_per_turn",
) -> AdminStatus:
    ok = ComponentStatus(state=ComponentState.OK, detail="available")
    reasoning_value = reasoning or ReasoningComponentStatus(
        state=ComponentState.OK,
        detail="operational",
        protocol="app-server-jsonl-v2",
        runtime_version="0.149.0",
        model="test-model",
    )
    return AdminStatus(
        readiness="FULLY_READY",
        checked_at=datetime(2026, 8, 23, 21, 0, tzinfo=UTC),
        components=RuntimeComponents(
            runtime=ComponentStatus(state=ComponentState.OK, detail="running"),
            assistant_database=ok,
            migrations=MigrationStatus(
                state=ComponentState.OK,
                detail="at_head",
                current_revision="0011_m7_03_runtime_configuration",
                expected_revision="0011_m7_03_runtime_configuration",
            ),
            configuration=configuration
            or ComponentStatus(state=ComponentState.OK, detail="valid"),
            source=source or ComponentStatus(state=ComponentState.OK, detail="operational"),
            logs=logs or ComponentStatus(state=ComponentState.OK, detail="operational"),
            reasoning_engine=reasoning_value,
        ),
        workflow_capabilities=WorkflowCapabilities(
            query=ComponentStatus(state=ComponentState.OK, detail="validated_per_turn"),
            navigation=ComponentStatus(state=ComponentState.OK, detail="validated_per_turn"),
            knowledge=ComponentStatus(state=ComponentState.OK, detail="available"),
            how_to=ComponentStatus(state=ComponentState.OK, detail="validated_per_turn"),
            action=ComponentStatus(state=ComponentState.OK, detail=action_detail),
        ),
        pending_capabilities=(),
        instance=InstanceStatus(
            instance_id="odoo:test",
            fingerprint="sha256:test",
            capabilities={},
        ),
    )


def _entries(matrix):
    return {entry.key: entry for entry in matrix.entries}


def test_healthy_matrix_covers_required_components_and_workflows() -> None:
    matrix = build_admin_diagnostics_matrix(
        status=_status(),
        configuration=None,
        source_status=SourceStatusDiagnostics(
            state="DETECTED",
            scan_status="succeeded",
        ),
        knowledge_probe="available",
        action_authority_ready=True,
    )
    entries = _entries(matrix)

    assert matrix.schema_version == 1
    assert matrix.readiness == "FULLY_READY"
    assert {
        "service.endpoint",
        "service.machine_auth",
        "assistant.database",
        "assistant.migrations",
        "assistant.configuration",
        "instance.profile",
        "source.index",
        "source.scan",
        "logs.provider",
        "knowledge.index",
        "reasoning.codex",
        "action.authority",
        "workflow.explain",
        "workflow.query",
        "workflow.how_to",
        "workflow.action",
    } == set(entries)
    assert all(entry.state is DiagnosticState.OK for entry in matrix.entries)


def test_invalid_configuration_is_distinct_from_provider_unavailable() -> None:
    matrix = build_admin_diagnostics_matrix(
        status=_status(
            configuration=ComponentStatus(state=ComponentState.ERROR, detail="invalid"),
            logs=ComponentStatus(state=ComponentState.PENDING, detail="unknown"),
        ),
        configuration=None,
        source_status=None,
        knowledge_probe="available",
        action_authority_ready=True,
    )
    entries = _entries(matrix)

    assert entries["assistant.configuration"].reason_code == "configuration_invalid"
    assert entries["logs.provider"].reason_code == "assistant_runtime_unavailable"
    assert matrix.readiness == "ERROR"


def test_codex_auth_and_action_authority_have_fixed_remediation() -> None:
    matrix = build_admin_diagnostics_matrix(
        status=_status(
            reasoning=ReasoningComponentStatus(
                state=ComponentState.PENDING,
                detail="auth_unavailable",
            ),
            action_detail="reasoning_unavailable",
        ),
        configuration=None,
        source_status=SourceStatusDiagnostics(state="DETECTED", scan_status="succeeded"),
        knowledge_probe="available",
        action_authority_ready=False,
    )
    entries = _entries(matrix)

    assert entries["reasoning.codex"].reason_code == "reasoning_auth_unavailable"
    assert (
        entries["reasoning.codex"].remediation_kind
        is DiagnosticRemediationKind.AUTHENTICATE_RUNTIME
    )
    assert entries["action.authority"].reason_code == "action_authority_unavailable"
    assert (
        entries["action.authority"].remediation_kind
        is DiagnosticRemediationKind.SETUP_REQUIRED
    )


def test_unknown_backend_detail_becomes_unrecognized_not_free_text() -> None:
    matrix = build_admin_diagnostics_matrix(
        status=_status(
            logs=ComponentStatus(state=ComponentState.ERROR, detail="backend-secret-canary"),
        ),
        configuration=None,
        source_status=SourceStatusDiagnostics(state="DETECTED", scan_status="succeeded"),
        knowledge_probe="available",
        action_authority_ready=True,
    )
    entry = _entries(matrix)["logs.provider"]
    rendered = matrix.model_dump_json()

    assert entry.reason_code == "status_unrecognized"
    assert "backend-secret-canary" not in rendered


def test_knowledge_failure_prevents_fully_ready_matrix() -> None:
    matrix = build_admin_diagnostics_matrix(
        status=_status(),
        configuration=None,
        source_status=SourceStatusDiagnostics(state="DETECTED", scan_status="succeeded"),
        knowledge_probe="unavailable",
        action_authority_ready=True,
    )

    assert matrix.readiness == "ERROR"
    assert _entries(matrix)["knowledge.index"].reason_code == "knowledge_index_unavailable"
