import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.contracts.maintenance import MaintenanceActor, MaintenanceEvent, MaintenanceJob, MaintenanceResult, MaintenanceStatus
from odoo_ai.runtime.maintenance import RuntimeMaintenanceError, RuntimeMaintenanceService

ADMIN_SECRET = "m7-maintenance-secret-" + "s" * 48
JOB_ID = UUID("12345678-1234-5678-1234-567812345678")
NOW = datetime(2026, 8, 24, tzinfo=UTC)


class StubMaintenanceService(RuntimeMaintenanceService):
    def __init__(self) -> None:
        self.reject_jobs = False

    async def readiness_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        return self._result("readiness_test", "readiness_ok", actor)

    async def source_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        return self._result("source_test", "source_test_succeeded", actor)

    async def logs_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        return self._result("logs_test", "logs_test_succeeded", actor)

    async def reasoning_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        return self._result("reasoning_test", "reasoning_operational", actor)

    async def configuration_revalidate(self, actor: MaintenanceActor) -> MaintenanceResult:
        return self._result("configuration_revalidate", "configuration_valid", actor)

    async def enqueue_source_rescan(self, actor: MaintenanceActor) -> MaintenanceJob:
        return self._enqueue("source_rescan", actor)

    async def enqueue_knowledge_reindex(self, actor: MaintenanceActor) -> MaintenanceJob:
        return self._enqueue("knowledge_reindex", actor)

    async def run_source_rescan_job(self, job_id: UUID) -> None:
        assert job_id == JOB_ID

    async def run_knowledge_reindex_job(self, job_id: UUID) -> None:
        assert job_id == JOB_ID

    async def status(self) -> MaintenanceStatus:
        return MaintenanceStatus(latest=(MaintenanceEvent(operation="readiness_test", state="succeeded", result_code="readiness_ok", checked_at=NOW),))

    async def job(self, job_id: UUID) -> MaintenanceJob:
        assert job_id == JOB_ID
        return MaintenanceJob(job_id=JOB_ID, operation="source_rescan", state="queued", created_at=NOW)

    def _result(self, operation: str, code: str, actor: MaintenanceActor) -> MaintenanceResult:
        assert actor.odoo_uid == 7
        assert actor.odoo_database == "odoo_m7"
        return MaintenanceResult.model_validate({"operation": operation, "state": "succeeded", "result_code": code, "checked_at": NOW, "metrics": {}})

    def _enqueue(self, operation: str, actor: MaintenanceActor) -> MaintenanceJob:
        assert actor.odoo_uid == 7
        assert actor.odoo_database == "odoo_m7"
        if self.reject_jobs:
            raise RuntimeMaintenanceError("maintenance_job_active", 409)
        return MaintenanceJob.model_validate({"job_id": JOB_ID, "operation": operation, "state": "queued", "created_at": NOW})


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{ADMIN_SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


async def _request(method: str, path: str, *, service: RuntimeMaintenanceService, payload: object | None = None, secret: str | None = ADMIN_SECRET, content: bytes | None = None) -> Response:
    transport = ASGITransport(app=create_app(maintenance_service=service))
    headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers, json=payload if content is None else None, content=content)


def _actor_payload() -> dict[str, object]:
    return {"actor": {"odoo_uid": 7, "odoo_database": "odoo_m7"}}


def test_explicit_routes_require_auth_and_do_not_expose_retired_action_dispatch() -> None:
    service = StubMaintenanceService()
    missing = asyncio.run(_request("POST", "/v1/admin/maintenance/readiness/test", service=service, payload=_actor_payload(), secret=None))
    assert missing.status_code == 401
    paths = (
        "/v1/admin/maintenance/readiness/test",
        "/v1/admin/maintenance/source/rescan",
        "/v1/admin/maintenance/source/test",
        "/v1/admin/maintenance/logs/test",
        "/v1/admin/maintenance/knowledge/reindex",
        "/v1/admin/maintenance/reasoning/test",
        "/v1/admin/maintenance/configuration/revalidate",
    )
    for path in paths:
        response = asyncio.run(_request("POST", path, service=service, payload=_actor_payload()))
        assert response.status_code == 200
        assert ADMIN_SECRET not in response.text
    retired = asyncio.run(_request("POST", "/v1/admin/maintenance/action/self-test", service=service, payload=_actor_payload()))
    assert retired.status_code == 404
    unknown = asyncio.run(_request("POST", "/v1/admin/maintenance/run", service=service, payload={"operation": "shell", **_actor_payload()}))
    assert unknown.status_code == 404


def test_status_and_job_are_bounded_machine_authenticated_views() -> None:
    service = StubMaintenanceService()
    status = asyncio.run(_request("GET", "/v1/admin/maintenance/status", service=service))
    job = asyncio.run(_request("GET", f"/v1/admin/maintenance/jobs/{JOB_ID}", service=service))
    assert status.status_code == 200
    assert status.json()["latest"][0]["result_code"] == "readiness_ok"
    assert job.status_code == 200
    assert job.json()["operation"] == "source_rescan"


def test_invalid_oversized_and_duplicate_requests_fail_closed() -> None:
    service = StubMaintenanceService()
    invalid = asyncio.run(_request("POST", "/v1/admin/maintenance/readiness/test", service=service, payload={**_actor_payload(), "operation": "reasoning_test"}))
    oversized = asyncio.run(_request("POST", "/v1/admin/maintenance/logs/test", service=service, content=b"{" + b"x" * 9000 + b"}"))
    service.reject_jobs = True
    duplicate = asyncio.run(_request("POST", "/v1/admin/maintenance/source/rescan", service=service, payload=_actor_payload()))
    assert invalid.status_code == 422
    assert oversized.status_code == 413
    assert duplicate.status_code == 409
    assert duplicate.json() == {"error": {"code": "maintenance_job_active"}, "ok": False}
