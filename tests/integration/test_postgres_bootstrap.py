import getpass
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from installer.bootstrap.postgres import PostgresBootstrapper, PostgresSettings


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@pytest.mark.skipif(
    os.environ.get("ODOO_AI_RUN_POSTGRES_BOOTSTRAP_TEST") != "1",
    reason="set ODOO_AI_RUN_POSTGRES_BOOTSTRAP_TEST=1 for the real cluster smoke",
)
def test_managed_postgres_first_second_run_and_isolation(tmp_path: Path) -> None:
    postgres_bin = Path("/usr/lib/postgresql/16/bin")
    initdb = postgres_bin / "initdb"
    pg_ctl = postgres_bin / "pg_ctl"
    psql = Path(shutil.which("psql") or "")
    if not initdb.is_file() or not pg_ctl.is_file() or not psql.is_file():
        pytest.skip("PostgreSQL 16 server/client binaries are unavailable")

    data_dir = tmp_path / "cluster"
    socket_dir = tmp_path / "socket"
    socket_dir.mkdir()
    port = _free_port()
    subprocess.run(
        [
            str(initdb),
            "--auth=trust",
            "--no-locale",
            "--encoding=UTF8",
            "--pgdata",
            str(data_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            str(pg_ctl),
            "--pgdata",
            str(data_dir),
            "--options",
            f"-p {port} -k {socket_dir} -h 127.0.0.1",
            "--log",
            str(data_dir / "postgres.log"),
            "--wait",
            "start",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        subprocess.run(
            [
                str(psql),
                "--host",
                str(socket_dir),
                "--port",
                str(port),
                "--dbname",
                "postgres",
                "--command",
                "CREATE DATABASE odoo_task_test",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        settings = PostgresSettings(
            database_name="assistant_task_test",
            role_name="assistant_task_role",
            host="127.0.0.1",
            port=port,
            admin_host=str(socket_dir),
            odoo_database_names=("odoo_task_test",),
            odoo_os_user=getpass.getuser(),
            alembic_config=Path(__file__).parents[2] / "alembic.ini",
            psql_path=psql,
            postgres_os_user=getpass.getuser(),
            backup_dir=tmp_path / "backups",
        )
        manager = PostgresBootstrapper(
            settings=settings,
            password="integration-password-" + "x" * 48,
            command_prefix=(),
        )

        first = manager.ensure()
        second = manager.ensure()
        migration_environment = os.environ.copy()
        migration_environment["ODOO_AI_DATABASE_URL"] = first.runtime_url
        migration_environment["ODOO_AI_DATABASE_NAME"] = settings.database_name
        subprocess.run(
            [
                str(Path(__file__).parents[2] / ".venv/bin/python"),
                "-m",
                "alembic",
                "-c",
                str(settings.alembic_config),
                "downgrade",
                "0001_m1_02_baseline",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=migration_environment,
        )
        upgraded = manager.ensure()

        assert first.database_created and first.role_created and first.hba_changed
        assert first.isolation_verified and first.migrations_applied
        assert not second.database_created and not second.role_created and not second.hba_changed
        assert second.isolation_verified and second.migrations_applied
        assert upgraded.backup_path is not None
        assert Path(upgraded.backup_path).is_file()
        assert Path(upgraded.backup_path).stat().st_mode & 0o077 == 0
        assert "assistant_task_role" in (data_dir / "pg_hba.conf").read_text()
    finally:
        subprocess.run(
            [str(pg_ctl), "--pgdata", str(data_dir), "--wait", "stop"],
            check=False,
            capture_output=True,
            text=True,
        )
