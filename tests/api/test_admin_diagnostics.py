import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, Response

from odoo_ai.api import create_app
from odoo_ai.contracts.admin_diagnostics import (
    AdminDiagnosticEntry,
    AdminDiagnosticsMatrix,
    DiagnosticRemediationKind,
    DiagnosticScope,
    DiagnosticSeverity,
    DiagnosticState,
)
from odoo_ai.runtime.admin_diagnostics import RuntimeAdminDiagnosticsService

ADMIN_SECRET = "m7-diagnostics-secret-" + "s" * 48


class StubAdminDiagnosticsService(RuntimeAdminDiagnosticsService):
    async def inspect(self) -> AdminDiagnosticsMatrix:
        checked_at = datetime(2026, 8, 23, 21, 0, tzinfo=UTC)
        return AdminDiagnosticsMatrix(
            readiness="DEGRADED",
            checked_at=checked_at,
            config_revision=7,
            entries=(
                AdminDiagnosticEntry(
                    key="reasoning.codex",
                    scope=DiagnosticScope.COMPONENT,
                    state=DiagnosticState.DEGRADED,
                    severity=DiagnosticSeverity.WARNING,
                    reason_code="reasoning_auth_unavailable",
                    summary="Codex runtime authentication is unavailable.",
                    checked_at=checked_at,
                    config_revision=7,
                    remediation_kind=DiagnosticRemediationKind.AUTHENTICATE_RUNTIME,
                    remediation_text="Authenticate Codex as the Assistant operating-system user.",
                ),
            ),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{ADMIN_SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


async def _get(
    *,
    service: RuntimeAdminDiagnosticsService,
    secret: str | None = ADMIN_SECRET,
) -> Response:
    transport = ASGITransport(app=create_app(admin_diagnostics_service=service))
    headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/v1/admin/diagnostics", headers=headers)


def test_structured_diagnostics_requires_machine_auth() -> None:
    service = StubAdminDiagnosticsService()

    missing = asyncio.run(_get(service=service, secret=None))
    wrong = asyncio.run(_get(service=service, secret="wrong-secret"))
    response = asyncio.run(_get(service=service))

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert response.status_code == 200
    assert response.json()["schema_version"] == 1
    assert response.json()["config_revision"] == 7
    assert ADMIN_SECRET not in missing.text
    assert ADMIN_SECRET not in wrong.text
    assert ADMIN_SECRET not in response.text


def test_structured_diagnostics_response_is_bounded_and_typed() -> None:
    response = asyncio.run(_get(service=StubAdminDiagnosticsService()))
    payload = response.json()

    assert payload["readiness"] == "DEGRADED"
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["key"] == "reasoning.codex"
    assert payload["entries"][0]["reason_code"] == "reasoning_auth_unavailable"
    assert payload["entries"][0]["remediation_kind"] == "authenticate_runtime"
