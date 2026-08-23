import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from odoo_ai.contracts import SourceScanDiagnostics, SourceScanMetricsView
from odoo_ai.contracts.maintenance import MaintenanceActor
from odoo_ai.runtime.maintenance import RuntimeMaintenanceError, RuntimeMaintenanceService
from odoo_ai.storage import DatabaseSettings, create_database_engine, create_instance_profile
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"


class FakeSourceDiagnostics:
    async def rescan_source(self) -> SourceScanDiagnostics:
        return SourceScanDiagnostics(
            state="DETECTED",
            scan_id=uuid4(),
            fingerprint="sha256:" + "a" * 64,
            metrics=SourceScanMetricsView(
                modules=2,
                files_seen=7,
                files_extracted=4,
                files_unchanged=3,
                bytes_hashed=1024,
                stale_files=0,
            ),
        )


@pytest.fixture
def migrated_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    command.upgrade(Config(REPO_ROOT / "alembic.ini"), "head")
    engine = create_database_engine(DatabaseSettings.from_env())
    yield engine
    engine.dispose()


def _create_latest_profile(engine: Engine) -> None:
    with engine.begin() as connection:
        session = Session(bind=connection, expire_on_commit=False)
        try:
            create_instance_profile(
                session,
                instance_id=f"maintenance-{uuid4()}",
                fingerprint=f"sha256:maintenance-{uuid4().hex}",
            )
            session.flush()
        finally:
            session.close()


def _actor() -> MaintenanceActor:
    return MaintenanceActor(odoo_uid=9, odoo_database="m7_maintenance_test")


def test_async_job_duplicate_control_and_source_result_are_bounded(
    migrated_engine: Engine,
) -> None:
    service = RuntimeMaintenanceService(
        database_settings=DatabaseSettings.from_env(),
        diagnostics_factory=FakeSourceDiagnostics,
    )
    first = asyncio.run(service.enqueue_source_rescan(_actor()))
    with pytest.raises(RuntimeMaintenanceError) as duplicate:
        asyncio.run(service.enqueue_source_rescan(_actor()))
    assert duplicate.value.code == "maintenance_job_active"

    asyncio.run(service.run_source_rescan_job(first.job_id))
    completed = asyncio.run(service.job(first.job_id))
    assert completed.state == "succeeded"
    assert completed.result_code == "source_rescan_succeeded"
    assert completed.metrics.source_files_seen == 7


def test_knowledge_reindex_failure_is_retryable_and_rebuild_is_idempotent(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _create_latest_profile(migrated_engine)
    root = tmp_path / "non-default knowledge maintenance root"
    environ = dict(os.environ)
    environ["ODOO_AI_KNOWLEDGE_SOURCES"] = json.dumps(
        [{"provider_id": "pilot.docs", "root": str(root), "locale": "es-ES"}]
    )
    service = RuntimeMaintenanceService(
        database_settings=DatabaseSettings.from_env(environ),
        environ=environ,
    )

    failed = asyncio.run(service.enqueue_knowledge_reindex(_actor()))
    asyncio.run(service.run_knowledge_reindex_job(failed.job_id))
    failed_state = asyncio.run(service.job(failed.job_id))
    assert failed_state.state == "failed"
    assert failed_state.result_code == "knowledge_reindex_incomplete"

    root.mkdir()
    (root / "guide.md").write_text(
        "# Pilot guide\n\nUse bounded maintenance from Odoo diagnostics.\n",
        encoding="utf-8",
    )
    first = asyncio.run(service.enqueue_knowledge_reindex(_actor()))
    asyncio.run(service.run_knowledge_reindex_job(first.job_id))
    first_state = asyncio.run(service.job(first.job_id))
    assert first_state.state == "succeeded"
    assert first_state.result_code == "knowledge_reindex_succeeded"
    assert first_state.metrics.knowledge_documents_indexed == 1

    second = asyncio.run(service.enqueue_knowledge_reindex(_actor()))
    asyncio.run(service.run_knowledge_reindex_job(second.job_id))
    second_state = asyncio.run(service.job(second.job_id))
    assert second_state.state == "succeeded"
    assert second_state.metrics.knowledge_documents_unchanged == 1

    with migrated_engine.connect() as connection:
        current = connection.scalar(
            text("SELECT count(*) FROM knowledge_document WHERE status = 'current'")
        )
    assert current is not None and current >= 1


def test_action_self_test_writes_only_sanitized_assistant_audit(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    canary = "M7-ACTION-CANARY-" + "z" * 64
    secret_file = tmp_path / "action-authority"
    secret_file.write_text(canary, encoding="utf-8")
    secret_file.chmod(0o600)
    environ = dict(os.environ)
    environ["ODOO_AI_ACTION_AUTHORITY_SECRET_FILE"] = str(secret_file)
    service = RuntimeMaintenanceService(
        database_settings=DatabaseSettings.from_env(environ),
        environ=environ,
    )

    result = asyncio.run(service.action_self_test(_actor()))
    assert result.state == "succeeded"
    assert result.result_code == "action_self_test_succeeded"
    assert canary not in result.model_dump_json()

    with migrated_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT operation, state, result_code, metrics::text "
                "FROM maintenance_audit_event "
                "WHERE operation = 'action_self_test' ORDER BY id DESC LIMIT 5"
            )
        ).all()
    assert rows
    assert canary not in repr(rows)
