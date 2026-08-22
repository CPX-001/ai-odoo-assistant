import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from odoo_ai.storage import DatabaseSettings, create_database_engine
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"


def _configure_test_database(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")

    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    return DatabaseSettings.from_env()


def test_connection_and_upgrade_head_are_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _configure_test_database(monkeypatch)
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    expected_head = ScriptDirectory.from_config(config).get_current_head()
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            current_database = connection.scalar(text("SELECT current_database()"))
            current_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()

    assert current_database == settings.database_name
    assert current_revision == expected_head


def test_upgrade_from_previous_revision_creates_source_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _configure_test_database(monkeypatch)
    config = Config(REPO_ROOT / "alembic.ini")
    command.downgrade(config, "0002_m1_03_runtime_tables")
    command.upgrade(config, "head")

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            tables = set(
                connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public'"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()

    assert {"scan_run", "source_file", "source_symbol", "xml_record"} <= tables


def test_fresh_database_upgrade_reaches_current_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _configure_test_database(monkeypatch)
    config = Config(REPO_ROOT / "alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()

    assert revision == ScriptDirectory.from_config(config).get_current_head()
