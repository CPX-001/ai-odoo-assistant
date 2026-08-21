import pytest

from odoo_ai.storage.config import (
    DATABASE_NAME_ENV,
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
    DatabaseSettings,
)


def test_database_settings_accept_expected_postgresql_database() -> None:
    settings = DatabaseSettings.from_env(
        {
            DATABASE_URL_ENV: "postgresql+psycopg://service:secret@db/odoo_ai",
            DATABASE_NAME_ENV: "odoo_ai",
        }
    )

    assert settings.database_name == "odoo_ai"
    assert settings.url.get_backend_name() == "postgresql"
    assert "secret" not in repr(settings)


@pytest.mark.parametrize(
    ("environ", "message"),
    [
        ({}, "ODOO_AI_DATABASE_URL is required"),
        (
            {DATABASE_URL_ENV: "sqlite:///odoo_ai.db"},
            "Assistant database must use PostgreSQL",
        ),
        (
            {DATABASE_URL_ENV: "postgresql+psycopg://service:secret@db/odoo"},
            "Configured URL does not target the expected Assistant database",
        ),
    ],
)
def test_database_settings_reject_missing_or_wrong_database(
    environ: dict[str, str], message: str
) -> None:
    with pytest.raises(DatabaseConfigurationError, match=message) as captured:
        DatabaseSettings.from_env(environ)

    assert "secret" not in str(captured.value)
