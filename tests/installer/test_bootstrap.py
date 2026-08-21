import os
import stat
from pathlib import Path

from installer.bootstrap.bootstrap import (
    AccountState,
    BootstrapPaths,
    Bootstrapper,
    ServiceSettings,
)
from installer.bootstrap.discovery import LinuxHost, OdooDeployment, OdooService
from installer.bootstrap.postgres import PostgresBootstrapResult


class FakeAccountManager:
    def __init__(self) -> None:
        self.calls = 0

    def ensure(self, *, user: str, group: str, home: Path, shared_reader_user: str) -> AccountState:
        self.calls += 1
        assert (user, group, shared_reader_user) == ("odoo-ai", "odoo-ai", "odoo")
        return AccountState(
            uid=os.getuid(),
            gid=os.getgid(),
            user_created=self.calls == 1,
            group_created=self.calls == 1,
            reader_added=self.calls == 1,
        )


class FakeDatabaseManager:
    def __init__(self, password: str) -> None:
        self.password = password

    def ensure(self) -> PostgresBootstrapResult:
        return PostgresBootstrapResult(
            mode="managed-local",
            database_created=True,
            role_created=True,
            hba_changed=True,
            isolation_verified=True,
            migrations_applied=True,
            runtime_url=(
                "postgresql+psycopg://odoo_ai_service:"
                f"{self.password}@db.internal:5544/customer_ai"
            ),
        )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_bootstrap_first_run_and_second_run_are_idempotent(tmp_path: Path) -> None:
    paths = BootstrapPaths(
        install_dir=tmp_path / "opt" / "odoo-ai-assistant",
        config_dir=tmp_path / "etc" / "odoo-ai-assistant",
        state_dir=tmp_path / "var" / "lib" / "odoo-ai-assistant",
        runtime_dir=tmp_path / "run" / "odoo-ai-assistant",
    )
    deployment = OdooDeployment(
        config_path=Path("/etc/odoo-server.conf"),
        addons_paths=(Path("/odoo/custom/addons"),),
        database_user="odoo",
    )
    accounts = FakeAccountManager()
    bootstrapper = Bootstrapper(
        paths=paths,
        account_manager=accounts,
        privileged_uid=os.getuid(),
        secret_factory=lambda: "s" * 64,
    )
    arguments = {
        "host": LinuxHost(distribution_id="ubuntu", version_id="24.04"),
        "deployment": deployment,
        "odoo_service": OdooService(unit="odoo-server.service", user="odoo"),
    }

    first = bootstrapper.run(**arguments)
    secret_before = paths.shared_secret.read_text(encoding="utf-8")
    second = bootstrapper.run(**arguments)

    assert first.user_created and first.group_created and first.secret_created
    assert not second.user_created and not second.group_created and not second.secret_created
    assert second.directories_created == ()
    assert not second.config_changed
    assert paths.shared_secret.read_text(encoding="utf-8") == secret_before
    assert _mode(paths.config_dir) == 0o750
    assert _mode(paths.state_dir) == 0o750
    assert _mode(paths.service_config) == 0o640
    assert _mode(paths.shared_secret) == 0o640
    config = paths.service_config.read_text(encoding="utf-8")
    assert 'ODOO_AI_HOST="127.0.0.1"' in config
    assert 'ODOO_AI_DATABASE_NAME="odoo_ai"' in config
    assert secret_before.strip() not in config


def test_bootstrap_customer_runtime_settings_and_paths_are_not_code_constants(tmp_path: Path) -> None:
    paths = BootstrapPaths(
        install_dir=tmp_path / "install with spaces",
        config_dir=tmp_path / "config with spaces",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
    )
    accounts = FakeAccountManager()
    bootstrapper = Bootstrapper(
        paths=paths,
        account_manager=accounts,
        service_settings=ServiceSettings(
            host="::1",
            port=8123,
            database_name="customer_ai",
            alembic_config=tmp_path / "migration config" / "alembic.ini",
        ),
        privileged_uid=os.getuid(),
        secret_factory=lambda: "z" * 64,
    )
    deployment = OdooDeployment(
        config_path=None,
        addons_paths=(Path("/srv/customer/addons"),),
        data_dir=Path("/srv/customer/data"),
        log_file=Path("/srv/customer/logs/odoo prod.log"),
    )

    result = bootstrapper.run(
        host=LinuxHost(distribution_id="debian", version_id="12"),
        deployment=deployment,
        odoo_service=OdooService(unit=None, user="odoo"),
    )

    assert result.odoo_config is None
    assert result.odoo_log_file == "/srv/customer/logs/odoo prod.log"
    config = paths.service_config.read_text(encoding="utf-8")
    assert 'ODOO_AI_HOST="::1"' in config
    assert 'ODOO_AI_PORT="8123"' in config
    assert 'ODOO_AI_DATABASE_NAME="customer_ai"' in config
    assert "migration config" in config


def test_bootstrap_repairs_safe_file_mode_drift_without_rotating_secret(
    tmp_path: Path,
) -> None:
    paths = BootstrapPaths(
        install_dir=tmp_path / "install",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
    )
    accounts = FakeAccountManager()
    bootstrapper = Bootstrapper(
        paths=paths,
        account_manager=accounts,
        privileged_uid=os.getuid(),
        secret_factory=lambda: "x" * 64,
    )
    deployment = OdooDeployment(
        config_path=Path("/etc/odoo.conf"),
        addons_paths=(Path("/odoo/addons"),),
    )
    arguments = {
        "host": LinuxHost(distribution_id="ubuntu", version_id="24.04"),
        "deployment": deployment,
        "odoo_service": OdooService(unit=None, user="odoo"),
    }
    bootstrapper.run(**arguments)
    secret_before = paths.shared_secret.read_bytes()
    paths.shared_secret.chmod(0o666)

    result = bootstrapper.run(**arguments)

    assert not result.secret_created
    assert paths.shared_secret.read_bytes() == secret_before
    assert _mode(paths.shared_secret) == 0o640


def test_bootstrap_persists_database_password_and_sanitized_result(tmp_path: Path) -> None:
    paths = BootstrapPaths(
        install_dir=tmp_path / "install",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        runtime_dir=tmp_path / "runtime",
    )
    accounts = FakeAccountManager()
    observed_passwords: list[str] = []

    def manager_factory(password: str) -> FakeDatabaseManager:
        observed_passwords.append(password)
        return FakeDatabaseManager(password)

    bootstrapper = Bootstrapper(
        paths=paths,
        account_manager=accounts,
        service_settings=ServiceSettings(database_name="customer_ai"),
        privileged_uid=os.getuid(),
        secret_factory=lambda: "p" * 64,
        database_manager_factory=manager_factory,
    )
    arguments = {
        "host": LinuxHost(distribution_id="ubuntu", version_id="24.04"),
        "deployment": OdooDeployment(
            config_path=None, database_names=("customer_odoo",)
        ),
        "odoo_service": OdooService(unit=None, user="odoo"),
    }

    first = bootstrapper.run(**arguments)
    second = bootstrapper.run(**arguments)

    assert first.database_password_created
    assert not second.database_password_created
    assert observed_passwords == ["p" * 64, "p" * 64]
    assert _mode(paths.database_password) == 0o640
    assert first.postgres_isolation_verified and first.migrations_applied
    assert "runtime_url" not in repr(first)
    service_config = paths.service_config.read_text(encoding="utf-8")
    assert 'ODOO_AI_DATABASE_URL="postgresql+psycopg://odoo_ai_service:' in service_config
