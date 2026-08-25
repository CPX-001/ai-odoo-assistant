import asyncio
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from odoo_ai.adapters import RuntimeDiagnosticsService
from odoo_ai.api import create_app
from odoo_ai.contracts import InstanceInventory
from odoo_ai.logs import FileLogProvider, LogFileOrigin, ResolvedLogFile
from odoo_ai.storage import DatabaseSettings
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPO_ROOT / "alembic.ini"
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"
ADMIN_SECRET = "m3-e2e-secret-" + "s" * 48


class FixtureInventoryGateway:
    def __init__(self, inventory: InstanceInventory) -> None:
        self._inventory = inventory

    async def get_instance_inventory(self) -> InstanceInventory:
        return self._inventory


@pytest.fixture
def database_settings(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    monkeypatch.setenv("ODOO_AI_ALEMBIC_CONFIG", str(ALEMBIC_CONFIG))
    command.upgrade(Config(ALEMBIC_CONFIG), "head")
    return DatabaseSettings.from_env()


def test_diagnostics_scan_source_log_traceback_and_staleness_e2e(
    database_settings: DatabaseSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "nondefault customer addons"
    fixture_source = REPO_ROOT / "tests/fixtures/odoo18/odoo_ai_m3_sale_project"
    module = source_root / fixture_source.name
    shutil.copytree(fixture_source, module)
    log_file = tmp_path / "customer logs" / "odoo production.log"
    log_file.parent.mkdir()
    shutil.copy2(REPO_ROOT / "tests/fixtures/logs/m3_odoo_traceback.txt", log_file)
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(ADMIN_SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))

    inventory = InstanceInventory(
        database=f"m3_fixture_{uuid4().hex}",
        server_version="18.0",
        installed_modules=(fixture_source.name,),
        addons_roots=(str(source_root),),
        captured_at="2026-08-22T10:00:00Z",
    )
    service = RuntimeDiagnosticsService(
        inventory_gateway_loader=lambda: FixtureInventoryGateway(inventory),
        database_settings=database_settings,
        log_provider=FileLogProvider(
            resolved=ResolvedLogFile(log_file.resolve(), LogFileOrigin.OVERRIDE)
        ),
        log_provider_name="file",
    )

    async def run_flow() -> None:
        transport = ASGITransport(app=create_app(diagnostics_service=service))
        headers = {"X-Odoo-AI-Shared-Secret": ADMIN_SECRET}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            scan = await client.post("/v1/admin/source/rescan", json={}, headers=headers)
            assert scan.status_code == 200
            first_scan = scan.json()
            assert first_scan["state"] == "DETECTED"
            assert first_scan["metrics"]["files_seen"] >= 3

            source = await client.post("/v1/admin/source/test", json={}, headers=headers)
            assert source.status_code == 200
            first_source = source.json()
            candidate = first_source["candidate"]
            assert candidate["module"] == "odoo_ai_m3_sale_project"
            assert candidate["logical_path"] == ("odoo_ai_m3_sale_project/models/sale_order.py")
            assert (candidate["start_line"], candidate["end_line"]) == (9, 28)
            excerpt = "\n".join(line["text"] for line in first_source["excerpt"]["lines"])
            assert "DIAGNOSTIC_ORDER_REFERENCE" in excerpt
            assert 'self.env["project.task"].create(values)' in excerpt
            assert str(source_root) not in source.text

            logs = await client.post(
                "/v1/admin/logs/test",
                json={
                    "from_ts": "2026-08-22T09:59:00Z",
                    "to_ts": "2026-08-22T10:02:00Z",
                    "terms": ["M3_DIAGNOSTIC_TRACEBACK"],
                    "max_lines": 20,
                    "max_bytes": 4096,
                },
                headers=headers,
            )
            assert logs.status_code == 200
            log_result = logs.json()["results"][0]
            traceback_fingerprint = log_result["traceback_fingerprint"]
            assert traceback_fingerprint.startswith("sha256:")
            assert "m3-fixture-secret-value" not in logs.text
            assert str(log_file) not in logs.text

            traceback = await client.post(
                "/v1/admin/logs/traceback",
                json={"fingerprint": traceback_fingerprint, "max_bytes": 4096},
                headers=headers,
            )
            assert traceback.status_code == 200
            assert "action_confirm" in traceback.json()["excerpt"]
            assert "password=<redacted>" in traceback.json()["excerpt"]

            status = await client.get("/v1/admin/status", headers=headers)
            assert status.status_code == 200
            assert status.json()["readiness"] == "DEGRADED"
            assert status.json()["components"]["source"]["state"] == "ok"
            assert status.json()["components"]["logs"]["state"] == "ok"
            assert status.json()["pending_capabilities"] == ["reasoning_engine"]

            source_path = module / "models/sale_order.py"
            original = source_path.read_text(encoding="utf-8")
            source_path.write_text(
                original.replace(
                    "order.client_order_ref != DIAGNOSTIC_ORDER_REFERENCE",
                    "order.client_order_ref not in {DIAGNOSTIC_ORDER_REFERENCE}",
                ),
                encoding="utf-8",
            )
            stale = await client.post("/v1/admin/source/test", json={}, headers=headers)
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "stale_source"

            rescan = await client.post("/v1/admin/source/rescan", json={}, headers=headers)
            assert rescan.status_code == 200
            assert rescan.json()["fingerprint"] != first_scan["fingerprint"]
            refreshed = await client.post("/v1/admin/source/test", json={}, headers=headers)
            assert refreshed.status_code == 200
            assert refreshed.json()["candidate"]["fingerprint"] != candidate["fingerprint"]

    asyncio.run(run_flow())
