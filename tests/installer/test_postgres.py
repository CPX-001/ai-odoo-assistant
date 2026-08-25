from pathlib import Path

import pytest

from installer.bootstrap.bootstrap import BootstrapError
from installer.bootstrap.postgres import PostgresBootstrapper, PostgresSettings


class ExternalExistingProbe(PostgresBootstrapper):
    def __init__(self, *, settings: PostgresSettings) -> None:
        super().__init__(settings=settings)
        self.connected = False
        self.migrated = False

    def _verify_runtime_connection(self, runtime_url: str) -> None:
        assert "customer_ai" in runtime_url
        self.connected = True

    def _run_migrations(self, runtime_url: str) -> None:
        assert self.connected
        self.migrated = True

    def _backup_before_pending_upgrade(self, runtime_url: str) -> str | None:
        return None


def test_external_existing_uses_protected_runtime_url_without_admin(tmp_path: Path) -> None:
    url_file = tmp_path / "database-url"
    url_file.write_text(
        "postgresql+psycopg://assistant:secret@db.internal:5544/customer_ai\n",
        encoding="utf-8",
    )
    url_file.chmod(0o600)
    manager = ExternalExistingProbe(
        settings=PostgresSettings(
            mode="external-existing",
            database_name="customer_ai",
            external_url_file=url_file,
        )
    )

    result = manager.ensure()

    assert result.mode == "external-existing"
    assert not result.database_created and not result.role_created
    assert not result.isolation_verified
    assert manager.connected and manager.migrated


def test_external_existing_rejects_world_readable_credentials(tmp_path: Path) -> None:
    url_file = tmp_path / "database-url"
    url_file.write_text(
        "postgresql+psycopg://assistant:secret@db/odoo_ai\n", encoding="utf-8"
    )
    url_file.chmod(0o644)

    with pytest.raises(BootstrapError, match="group/other"):
        ExternalExistingProbe(
            settings=PostgresSettings(
                mode="external-existing",
                external_url_file=url_file,
            )
        ).ensure()


@pytest.mark.parametrize("value", ["bad name", "db/name", "db\nname"])
def test_managed_mode_rejects_unsafe_database_identifiers(value: str) -> None:
    with pytest.raises(BootstrapError, match="identifier"):
        PostgresBootstrapper(
            settings=PostgresSettings(
                database_name=value,
                odoo_database_names=("odoo_prod",),
                odoo_os_user="odoo",
            ),
            password="p" * 64,
        ).ensure()
