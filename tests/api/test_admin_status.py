import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.runtime.status import AdminStatusService, ComponentState, InstanceStatus, ReasoningComponentStatus
from odoo_ai.storage import DatabaseSettings, create_capability_snapshot, create_database_engine, create_instance_profile, create_session_factory, session_scope
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV
from sqlalchemy import Engine

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPO_ROOT / "alembic.ini"
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"
ADMIN_SECRET = "test-admin-secret-" + "s" * 48


async def _get_status(secret: str | None = ADMIN_SECRET) -> Response:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers = {"X-Odoo-AI-Shared-Secret": secret} if secret is not None else {}
        return await client.get("/v1/admin/status", headers=headers)


@pytest.fixture(autouse=True)
def configured_admin_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{ADMIN_SECRET}\n", encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("ODOO_AI_CODEX_EXECUTABLE", raising=False)


@pytest.fixture
def configured_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    monkeypatch.setenv("ODOO_AI_ALEMBIC_CONFIG", str(ALEMBIC_CONFIG))
    command.upgrade(Config(ALEMBIC_CONFIG), "head")
    engine = create_database_engine(DatabaseSettings.from_env())
    yield engine
    engine.dispose()


def test_admin_status_reports_current_component_surface(configured_engine: Engine) -> None:
    session_factory = create_session_factory(configured_engine)
    with session_scope(session_factory) as session:
        profile = create_instance_profile(session, instance_id=f"status-{uuid4()}", fingerprint="sha256:status")
        create_capability_snapshot(session, instance_profile_id=profile.id, readiness="DEGRADED", capabilities={"runtime_http": True, "assistant_db": True})
    response = asyncio.run(_get_status())
    payload = response.json()
    assert response.status_code == 200
    assert payload["readiness"] == "DEGRADED"
    assert payload["components"]["runtime"] == {"state": "ok", "detail": "running"}
    assert payload["components"]["assistant_database"] == {"state": "ok", "detail": "available"}
    assert payload["components"]["migrations"]["detail"] == "at_head"
    assert payload["components"]["configuration"] == {"state": "ok", "detail": "valid"}
    assert payload["pending_capabilities"] == ["source", "logs", "reasoning_engine"]
    assert "workflow_capabilities" not in payload


def test_fully_ready_status_is_sanitized(configured_engine: Engine) -> None:
    session_factory = create_session_factory(configured_engine)
    with session_scope(session_factory) as session:
        profile = create_instance_profile(session, instance_id=f"fully-ready-{uuid4()}", fingerprint="sha256:fully-ready")
        create_capability_snapshot(session, instance_profile_id=profile.id, readiness="DEGRADED", capabilities={"source": "DETECTED", "logs": "OPERATIONAL", "log_provider": "file", "source_root": "/srv/private/addons", "shared_secret": "canary-secret"})
    status = AdminStatusService.from_env().inspect(reasoning=ReasoningComponentStatus(state=ComponentState.OK, detail="operational", protocol="app-server-jsonl-v2", runtime_version="0.149.0", model="configured-model"))
    serialized = status.model_dump_json()
    assert status.readiness == "FULLY_READY"
    assert status.pending_capabilities == ()
    assert status.instance is not None
    assert status.instance.capabilities["reasoning_engine"] == "OPERATIONAL"
    assert "/srv/private" not in serialized
    assert "canary-secret" not in serialized


def test_admin_status_sanitizes_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "must-not-appear"
    monkeypatch.setenv(DATABASE_URL_ENV, f"postgresql+psycopg://invalid:{secret}@127.0.0.1:1/odoo_ai_test?connect_timeout=1")
    monkeypatch.setenv(DATABASE_NAME_ENV, "odoo_ai_test")
    monkeypatch.setenv("ODOO_AI_ALEMBIC_CONFIG", str(ALEMBIC_CONFIG))
    response = asyncio.run(_get_status())
    assert response.status_code == 200
    assert response.json()["readiness"] == "ERROR"
    assert secret not in response.text
    assert "postgresql" not in response.text


def test_admin_status_requires_local_shared_secret() -> None:
    assert asyncio.run(_get_status(secret=None)).status_code == 401
    assert asyncio.run(_get_status(secret="wrong-secret")).status_code == 401


@pytest.mark.parametrize(("source_state", "component_state", "detail"), [("DETECTED", ComponentState.OK, "operational"), ("NOT_FOUND", ComponentState.PENDING, "not_found"), ("NO_PERMISSION", ComponentState.ERROR, "no_permission"), ("ERROR", ComponentState.ERROR, "error")])
def test_source_capability_states_remain_distinct(source_state: str, component_state: ComponentState, detail: str) -> None:
    instance = InstanceStatus(instance_id="customer", fingerprint="sha256:instance", capabilities={"source": source_state})
    status = AdminStatusService._source_status(instance)
    assert status.state is component_state
    assert status.detail == detail
