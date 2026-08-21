import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import Engine, text

from odoo_ai.api import create_app
from odoo_ai.storage import (
    DatabaseSettings,
    create_capability_snapshot,
    create_database_engine,
    create_instance_profile,
    create_session_factory,
    session_scope,
)
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

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


def test_admin_status_reports_runtime_db_migrations_and_profile(
    configured_engine: Engine,
) -> None:
    instance_id = f"status-{uuid4()}"
    session_factory = create_session_factory(configured_engine)
    with session_scope(session_factory) as session:
        profile = create_instance_profile(
            session, instance_id=instance_id, fingerprint="sha256:status"
        )
        create_capability_snapshot(
            session,
            instance_profile_id=profile.id,
            readiness="DEGRADED",
            capabilities={"runtime_http": True, "assistant_db": True},
        )

    response = asyncio.run(_get_status())
    payload = response.json()

    assert response.status_code == 200
    assert payload["readiness"] == "DEGRADED"
    assert payload["components"]["runtime"] == {"state": "ok", "detail": "running"}
    assert payload["components"]["assistant_database"] == {
        "state": "ok",
        "detail": "available",
    }
    assert payload["components"]["migrations"]["state"] == "ok"
    assert payload["components"]["migrations"]["detail"] == "at_head"
    assert payload["instance"]["instance_id"] == instance_id
    assert payload["pending_capabilities"] == ["source", "logs", "reasoning_engine"]


def test_admin_status_sanitizes_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "must-not-appear"
    monkeypatch.setenv(
        DATABASE_URL_ENV,
        f"postgresql+psycopg://invalid:{secret}@127.0.0.1:1/odoo_ai_test?connect_timeout=1",
    )
    monkeypatch.setenv(DATABASE_NAME_ENV, "odoo_ai_test")
    monkeypatch.setenv("ODOO_AI_ALEMBIC_CONFIG", str(ALEMBIC_CONFIG))

    response = asyncio.run(_get_status())
    payload = response.json()

    assert response.status_code == 200
    assert payload["readiness"] == "ERROR"
    assert payload["components"]["assistant_database"] == {
        "state": "error",
        "detail": "unavailable",
    }
    assert secret not in response.text
    assert "postgresql" not in response.text


def test_admin_status_reports_migration_mismatch(configured_engine: Engine) -> None:
    config = Config(ALEMBIC_CONFIG)
    with configured_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = '0001_m1_02_baseline'"))
    try:
        response = asyncio.run(_get_status())
        payload = response.json()

        assert response.status_code == 200
        assert payload["readiness"] == "ERROR"
        assert payload["components"]["migrations"]["state"] == "error"
        assert payload["components"]["migrations"]["detail"] == "revision_mismatch"
        assert payload["components"]["migrations"]["current_revision"] == ("0001_m1_02_baseline")
        assert payload["instance"] is None
    finally:
        command.stamp(config, "head")


def test_admin_status_requires_the_local_shared_secret() -> None:
    missing = asyncio.run(_get_status(secret=None))
    wrong = asyncio.run(_get_status(secret="wrong-secret"))

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert ADMIN_SECRET not in missing.text
    assert ADMIN_SECRET not in wrong.text
