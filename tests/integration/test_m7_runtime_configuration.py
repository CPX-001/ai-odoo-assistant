import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings
from odoo_ai.contracts.admin_configuration import AdminConfigurationActor
from odoo_ai.contracts.configuration import AssistantAdminOverrides
from odoo_ai.logs.configured import journal_unit_override_from_env, log_file_override_from_env
from odoo_ai.runtime.configuration import (
    LOG_FILE_ENV,
    SOURCE_ROOTS_ENV,
    RuntimeConfigurationError,
    RuntimeConfigurationService,
)
from odoo_ai.source.configured import source_root_overrides_from_env
from odoo_ai.storage import (
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV
from odoo_ai.storage.configuration_repository import (
    list_runtime_config_audit_events,
    read_runtime_configuration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPO_ROOT / "alembic.ini"
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"


@pytest.fixture
def runtime_config_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Engine, Path, Path, Path, Path]]:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    monkeypatch.setenv("ODOO_AI_ALEMBIC_CONFIG", str(ALEMBIC_CONFIG))

    authorized = tmp_path / "customer-layout" / "addons"
    selected = authorized / "custom"
    outside = tmp_path / "outside"
    authorized.mkdir(parents=True)
    selected.mkdir()
    outside.mkdir()
    log_file = tmp_path / "customer-layout" / "logs" / "odoo.log"
    log_file.parent.mkdir(parents=True)
    log_file.write_text("ready\n", encoding="utf-8")
    monkeypatch.setenv(SOURCE_ROOTS_ENV, json.dumps([str(authorized)]))
    monkeypatch.setenv(LOG_FILE_ENV, str(log_file))
    monkeypatch.delenv("ODOO_AI_JOURNAL_UNIT", raising=False)
    monkeypatch.delenv("ODOO_AI_CODEX_MODEL", raising=False)
    monkeypatch.delenv("ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS", raising=False)

    secret_file = tmp_path / "machine-secret"
    secret_file.write_text(
        "canary-secret-value-that-must-never-be-returned\n",
        encoding="utf-8",
    )
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))

    command.upgrade(Config(ALEMBIC_CONFIG), "head")
    engine = create_database_engine(DatabaseSettings.from_env())
    _reset_configuration(engine)
    try:
        yield engine, authorized, selected, outside, log_file
    finally:
        _reset_configuration(engine)
        engine.dispose()


def test_runtime_configuration_apply_is_atomic_and_hot(
    runtime_config_environment: tuple[Engine, Path, Path, Path, Path],
) -> None:
    engine, _authorized, selected, outside, log_file = runtime_config_environment
    service = RuntimeConfigurationService.from_env()
    actor = AdminConfigurationActor(odoo_uid=9, odoo_database="nondefault_customer")
    requested = AssistantAdminOverrides(
        source_roots=(str(selected),),
        log_provider="file",
        reasoning_model="gpt-5.6/codex",
        reasoning_startup_timeout_seconds=75.0,
        reasoning_turn_timeout_seconds=300.0,
    )

    initial = service.snapshot()
    validated = service.validate(requested)
    applied = service.apply(expected_revision=0, overrides=requested, actor=actor)

    assert initial.revision == 0
    assert initial.validation_state == "valid"
    assert validated.revision == 0
    assert validated.validation_state == "valid"
    assert applied.revision == 1
    assert applied.post_action == "none"
    assert applied.overrides.source_roots == (str(selected.resolve()),)
    assert "canary-secret-value" not in applied.model_dump_json()

    current = service.snapshot()
    assert current.revision == 1
    assert current.fingerprint == applied.fingerprint
    assert source_root_overrides_from_env() == (str(selected.resolve()),)
    assert log_file_override_from_env() == (str(log_file),)
    assert journal_unit_override_from_env(os.environ) == ()
    codex = ConfiguredCodexRuntimeSettings.from_env()
    assert codex.model == "gpt-5.6/codex"
    assert codex.startup_timeout_seconds == 75.0
    assert codex.turn_timeout_seconds == 300.0

    with pytest.raises(RuntimeConfigurationError) as invalid_error:
        service.apply(
            expected_revision=1,
            overrides=requested.model_copy(update={"source_roots": (str(outside),)}),
            actor=actor,
        )
    assert invalid_error.value.code == "configuration_invalid"
    assert service.snapshot().revision == 1

    with pytest.raises(RuntimeConfigurationError) as stale_error:
        service.apply(expected_revision=0, overrides=requested, actor=actor)
    assert stale_error.value.code == "configuration_revision_conflict"
    assert service.snapshot().revision == 1

    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        stored = read_runtime_configuration(session)
        events = list_runtime_config_audit_events(session)
    assert stored.revision == 1
    assert stored.overrides["reasoning_model"] == "gpt-5.6/codex"
    assert len(events) == 1
    assert events[0]["event_type"] == "configuration_applied"
    changed_keys = events[0]["changed_keys"]
    assert isinstance(changed_keys, list)
    assert "reasoning.model" in changed_keys
    assert "gpt-5.6/codex" not in json.dumps(events)
    assert "canary-secret-value" not in json.dumps(events)


def test_runtime_configuration_rejects_unavailable_provider(
    runtime_config_environment: tuple[Engine, Path, Path, Path, Path],
) -> None:
    service = RuntimeConfigurationService.from_env()

    with pytest.raises(RuntimeConfigurationError) as error:
        service.validate(AssistantAdminOverrides(log_provider="journal"))

    assert error.value.code == "configuration_invalid"
    assert service.snapshot().revision == 0


def test_m7_migration_creates_configuration_state_tables(
    runtime_config_environment: tuple[Engine, Path, Path, Path, Path],
) -> None:
    engine = runtime_config_environment[0]
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        state = connection.execute(
            text(
                "SELECT current_revision, current_fingerprint "
                "FROM runtime_config_state WHERE id = 1"
            )
        ).one()

    assert {
        "runtime_config_state",
        "runtime_config_revision",
        "runtime_config_audit_event",
    } <= tables
    assert tuple(state) == (0, None)


def _reset_configuration(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM runtime_config_audit_event"))
        connection.execute(text("DELETE FROM runtime_config_revision"))
        connection.execute(
            text(
                "UPDATE runtime_config_state SET current_revision = 0, "
                "current_fingerprint = NULL"
            )
        )
