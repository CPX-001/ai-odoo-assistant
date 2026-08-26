import os
import pwd
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest
from installer.bootstrap.bootstrap import (
    AccountState,
    BootstrapPaths,
    Bootstrapper,
    ServiceSettings,
)
from installer.bootstrap.discovery import LinuxHost, OdooDeployment, OdooService
from installer.bootstrap.postgres import PostgresBootstrapper, PostgresSettings
from installer.bootstrap.runtime import RuntimeInstaller, RuntimeInstallSettings
from installer.bootstrap.systemd import SystemdInstaller, SystemdSettings


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


class ExistingAccountManager:
    def __init__(self, *, uid: int, gid: int) -> None:
        self._uid = uid
        self._gid = gid

    def ensure(
        self, *, user: str, group: str, home: Path, shared_reader_user: str
    ) -> AccountState:
        assert user == "nobody"
        assert group == "nogroup"
        assert shared_reader_user != "root"
        return AccountState(
            uid=self._uid,
            gid=self._gid,
            user_created=False,
            group_created=False,
            reader_added=False,
        )


@pytest.mark.skipif(
    os.environ.get("ODOO_AI_RUN_NONDEFAULT_BOOTSTRAP_TEST") != "1"
    or os.geteuid() != 0,
    reason="set ODOO_AI_RUN_NONDEFAULT_BOOTSTRAP_TEST=1 and run as root",
)
def test_full_nondefault_bootstrap_upgrade_and_rollback() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    postgres_bin = Path("/usr/lib/postgresql/16/bin")
    if not (postgres_bin / "initdb").is_file() or not Path("/run/systemd/system").exists():
        pytest.skip("PostgreSQL 16 or real systemd is unavailable")
    operator = pwd.getpwuid(repo_root.stat().st_uid)
    if operator.pw_uid == 0:
        pytest.skip("repository owner must be a non-root disposable PostgreSQL operator")
    nobody = pwd.getpwnam("nobody")
    base = Path(tempfile.mkdtemp(prefix="odoo-ai-acme-bootstrap-", dir="/tmp"))
    base.chmod(0o755)

    suffix = str(os.getpid())
    unit_name = f"acme-assistant-{suffix}.service"
    unit_path = Path("/etc/systemd/system") / unit_name
    pg_area = base / "postgres-custom"
    pg_area.mkdir()
    os.chown(pg_area, operator.pw_uid, operator.pw_gid)
    data_dir = pg_area / "cluster"
    socket_dir = pg_area / "socket"
    socket_dir.mkdir()
    os.chown(socket_dir, operator.pw_uid, operator.pw_gid)
    pg_port = _free_port()

    def as_operator(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["runuser", "--user", operator.pw_name, "--", *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    as_operator(
        str(postgres_bin / "initdb"),
        "--auth=trust",
        "--no-locale",
        "--encoding=UTF8",
        "--pgdata",
        str(data_dir),
    )
    as_operator(
        str(postgres_bin / "pg_ctl"),
        "--pgdata",
        str(data_dir),
        "--options",
        f"-p {pg_port} -k {socket_dir} -h 127.0.0.1",
        "--log",
        str(data_dir / "postgres.log"),
        "--wait",
        "start",
    )

    paths = BootstrapPaths(
        install_dir=base / "assistant install with spaces",
        config_dir=base / "assistant-config-custom",
        state_dir=base / "assistant state",
        runtime_dir=base / "assistant runtime",
    )
    source = base / "runtime source"
    shutil.copytree(
        repo_root / "service",
        source / "service",
        ignore=shutil.ignore_patterns(".venv"),
    )
    shutil.copytree(repo_root / "migrations", source / "migrations")
    shutil.copy2(repo_root / "alembic.ini", source / "alembic.ini")
    runtime = RuntimeInstaller(
        settings=RuntimeInstallSettings(
            source_root=source,
            install_dir=paths.install_dir,
            python_executable=repo_root / ".venv/bin/python",
        )
    )
    assistant_database = f"acme_assistant_{suffix}"
    assistant_role = f"acme_role_{suffix}"
    odoo_database = f"acme_erp_{suffix}"
    as_operator(
        "/usr/bin/createdb",
        "--host",
        str(socket_dir),
        "--port",
        str(pg_port),
        odoo_database,
    )

    deployment = OdooDeployment(
        config_path=None,
        addons_paths=(base / "acme addons",),
        data_dir=base / "acme data",
        log_file=base / "acme logs/erp production.log",
        database_names=(odoo_database,),
    )
    odoo_service = OdooService(unit=None, user=operator.pw_name)
    accounts = ExistingAccountManager(uid=nobody.pw_uid, gid=nobody.pw_gid)

    def build(port: int, *, include_runtime: bool = True) -> Bootstrapper:
        postgres_settings = PostgresSettings(
            database_name=assistant_database,
            role_name=assistant_role,
            host="127.0.0.1",
            port=pg_port,
            admin_host=str(socket_dir),
            odoo_database_names=(odoo_database,),
            odoo_os_user=operator.pw_name,
            alembic_config=paths.install_dir / "current/alembic.ini",
            psql_path=Path("/usr/bin/psql"),
            postgres_os_user=operator.pw_name,
            backup_dir=base / "assistant backups",
        )
        systemd = SystemdInstaller(
            settings=SystemdSettings(
                unit_name=unit_name,
                unit_dir=unit_path.parent,
                template_path=repo_root
                / "installer/systemd/odoo-ai-assistant.service.in",
                service_user="nobody",
                service_group="nogroup",
                working_directory=paths.install_dir / "current",
                environment_file=paths.service_config,
                shared_secret_file=paths.shared_secret,
                executable=paths.install_dir / "current/.venv/bin/odoo-ai-service",
                host="127.0.0.1",
                port=port,
            )
        )
        return Bootstrapper(
            paths=paths,
            account_manager=accounts,
            service_user="nobody",
            service_group="nogroup",
            service_settings=ServiceSettings(
                host="127.0.0.1",
                port=port,
                database_name=assistant_database,
                alembic_config=paths.install_dir / "current/alembic.ini",
            ),
            secret_factory=lambda: "alternate-layout-secret-" + "s" * 48,
            database_manager_factory=lambda password: PostgresBootstrapper(
                settings=postgres_settings,
                password=password,
            ),
            systemd_manager=systemd,
            runtime_manager=runtime if include_runtime else None,
        )

    arguments = {
        "host": LinuxHost(distribution_id="ubuntu", version_id="24.04"),
        "deployment": deployment,
        "odoo_service": odoo_service,
    }
    first_port = _free_port()
    second_port = _free_port()
    try:
        bootstrap = build(first_port)
        first = bootstrap.run(**arguments)
        second = bootstrap.run(**arguments)
        assert first.runtime_release_created and first.database_created
        assert first.postgres_isolation_verified and first.migrations_applied
        assert first.service_active and first.health_verified and first.admin_status_verified
        assert not second.runtime_release_created and not second.runtime_current_changed
        assert not second.database_created and not second.config_changed
        assert not second.systemd_unit_changed and not second.service_restarted

        source_file = source / "service/src/odoo_ai/__init__.py"
        source_file.write_text(
            source_file.read_text(encoding="utf-8") + "\n# alternate upgrade\n",
            encoding="utf-8",
        )
        upgraded = build(second_port).run(**arguments)
        assert upgraded.runtime_current_changed and upgraded.config_changed
        assert upgraded.service_restarted and upgraded.health_verified

        runtime.activate_previous(schema_compatible=True)
        rolled_back = build(first_port, include_runtime=False).run(**arguments)
        assert rolled_back.config_changed and rolled_back.service_restarted
        assert rolled_back.health_verified and rolled_back.admin_status_verified
    finally:
        subprocess.run(
            ["systemctl", "disable", "--now", unit_name],
            check=False,
            capture_output=True,
            text=True,
        )
        unit_path.unlink(missing_ok=True)
        subprocess.run(
            ["systemctl", "daemon-reload"], check=False, capture_output=True, text=True
        )
        as_operator(
            str(postgres_bin / "pg_ctl"),
            "--pgdata",
            str(data_dir),
            "--wait",
            "stop",
        )
        if base.parent == Path("/tmp") and base.name.startswith(
            "odoo-ai-acme-bootstrap-"
        ):
            shutil.rmtree(base, ignore_errors=True)
