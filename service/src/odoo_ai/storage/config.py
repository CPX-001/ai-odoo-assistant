"""External database configuration with Assistant DB identity checks."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_ENV = "ODOO_AI_DATABASE_URL"
DATABASE_NAME_ENV = "ODOO_AI_DATABASE_NAME"
DEFAULT_DATABASE_NAME = "odoo_ai"


class DatabaseConfigurationError(ValueError):
    """Raised when Assistant database configuration is absent or unsafe."""


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Validated connection settings for the Assistant-owned PostgreSQL DB."""

    url: URL
    database_name: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DatabaseSettings":
        source = os.environ if environ is None else environ
        raw_url = source.get(DATABASE_URL_ENV)
        if not raw_url:
            raise DatabaseConfigurationError(f"{DATABASE_URL_ENV} is required")

        expected_name = source.get(DATABASE_NAME_ENV, DEFAULT_DATABASE_NAME).strip()
        if not expected_name:
            raise DatabaseConfigurationError(f"{DATABASE_NAME_ENV} cannot be empty")

        try:
            url = make_url(raw_url)
        except ArgumentError as error:
            raise DatabaseConfigurationError("Assistant database URL is invalid") from error

        if url.get_backend_name() != "postgresql":
            raise DatabaseConfigurationError("Assistant database must use PostgreSQL")
        if url.database != expected_name:
            raise DatabaseConfigurationError(
                "Configured URL does not target the expected Assistant database"
            )

        return cls(url=url, database_name=expected_name)
