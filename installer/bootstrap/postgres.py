"""PostgreSQL bootstrap for the Assistant-owned database.

The managed profile is intentionally narrow: it administers a PostgreSQL cluster
available through a local ``psql`` peer connection. Remote/managed PostgreSQL is
supported through the explicit ``external-existing`` mode, where the operator
provisions the database and supplies the runtime URL in a protected file.
"""

from __future__ import annotations

import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql
from sqlalchemy.engine import URL, make_url

from installer.bootstrap.bootstrap import BootstrapError

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$-]*$")
_HBA_BEGIN = "# BEGIN ODOO AI ASSISTANT MANAGED ISOLATION"
_HBA_END = "# END ODOO AI ASSISTANT MANAGED ISOLATION"


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    mode: Literal["managed-local", "external-existing"] = "managed-local"
    database_name: str = "odoo_ai"
    role_name: str = "odoo_ai_service"
    host: str = "127.0.0.1"
    port: int = 5432
    admin_host: str = "/var/run/postgresql"
    odoo_database_names: tuple[str, ...] = ()
    odoo_os_user: str | None = None
    alembic_config: Path = Path("alembic.ini")
    external_url_file: Path | None = None
    psql_path: Path = Path("/usr/bin/psql")
    postgres_os_user: str = "postgres"
    backup_dir: Path | None = None
    pg_dump_path: Path = Path("/usr/bin/pg_dump")


@dataclass(frozen=True, slots=True)
class PostgresBootstrapResult:
    mode: str
    database_created: bool
    role_created: bool
    hba_changed: bool
    isolation_verified: bool
    migrations_applied: bool
    runtime_url: str
    backup_path: str | None


class DatabaseBootstrapManager(Protocol):
    def ensure(self) -> PostgresBootstrapResult: ...


def _validate_identifier(value: str, *, label: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise BootstrapError(f"{label} must be a simple PostgreSQL identifier")
    return value


def _read_protected_url(path: Path, *, expected_database: str) -> str:
    try:
        metadata = path.stat()
        raw_url = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise BootstrapError("Cannot read the protected Assistant database URL file") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise BootstrapError("Assistant database URL path must be a regular file")
    if metadata.st_mode & 0o077:
        raise BootstrapError("Assistant database URL file must not be accessible by group/other")
    try:
        parsed = make_url(raw_url)
    except Exception as error:
        raise BootstrapError("Assistant database URL file is invalid") from error
    if parsed.get_backend_name() != "postgresql" or parsed.database != expected_database:
        raise BootstrapError("Assistant database URL does not target the configured PostgreSQL DB")
    return raw_url


def _runtime_url(settings: PostgresSettings, password: str) -> str:
    return URL.create(
        "postgresql+psycopg",
        username=settings.role_name,
        password=password,
        host=settings.host,
        port=settings.port,
        database=settings.database_name,
    ).render_as_string(hide_password=False)


def _psycopg_url(runtime_url: str, *, database: str | None = None) -> str:
    parsed = make_url(runtime_url)
    if database is not None:
        parsed = parsed.set(database=database)
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


class PostgresBootstrapper:
    """Create/check the Assistant DB and apply migrations without Odoo SQL access."""

    def __init__(
        self,
        *,
        settings: PostgresSettings,
        password: str | None = None,
        command_prefix: tuple[str, ...] | None = None,
    ) -> None:
        self._settings = settings
        self._password = password
        self._command_prefix = (
            ("runuser", "--user", settings.postgres_os_user, "--")
            if command_prefix is None
            else command_prefix
        )

    def ensure(self) -> PostgresBootstrapResult:
        settings = self._settings
        _validate_identifier(settings.database_name, label="Assistant database name")
        _validate_identifier(settings.role_name, label="Assistant role name")
        for name in settings.odoo_database_names:
            _validate_identifier(name, label="Odoo database name")
        if not 1 <= settings.port <= 65535:
            raise BootstrapError("Assistant PostgreSQL port must be between 1 and 65535")

        if settings.mode == "external-existing":
            if settings.external_url_file is None:
                raise BootstrapError(
                    "external-existing mode requires --assistant-database-url-file"
                )
            runtime_url = _read_protected_url(
                settings.external_url_file, expected_database=settings.database_name
            )
            self._verify_runtime_connection(runtime_url)
            backup_path = self._backup_before_pending_upgrade(runtime_url)
            self._run_migrations(runtime_url)
            return PostgresBootstrapResult(
                mode=settings.mode,
                database_created=False,
                role_created=False,
                hba_changed=False,
                isolation_verified=False,
                migrations_applied=True,
                runtime_url=runtime_url,
                backup_path=backup_path,
            )

        if self._password is None:
            raise BootstrapError("Managed PostgreSQL mode requires a persisted runtime password")
        if not settings.odoo_database_names:
            raise BootstrapError(
                "Managed same-cluster mode requires at least one explicit/discovered Odoo database"
            )

        role_created = not self._admin_exists(
            f"SELECT 1 FROM pg_roles WHERE rolname = "
            f"{sql.Literal(settings.role_name).as_string()}"
        )
        if role_created:
            self._admin_execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
                )
                .format(sql.Identifier(settings.role_name), sql.Literal(self._password))
                .as_string()
            )
        else:
            unsafe = self._admin_scalar(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR NOT rolcanlogin "
                f"FROM pg_roles WHERE rolname = "
                f"{sql.Literal(settings.role_name).as_string()}"
            )
            if unsafe != "f":
                raise BootstrapError("Existing Assistant PostgreSQL role has unsafe attributes")

        database_created = not self._admin_exists(
            f"SELECT 1 FROM pg_database WHERE datname = "
            f"{sql.Literal(settings.database_name).as_string()}"
        )
        if database_created:
            self._admin_execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(settings.database_name), sql.Identifier(settings.role_name)
                ).as_string()
            )
        self._admin_execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(settings.database_name)
            ).as_string()
        )
        self._admin_execute(
            sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                sql.Identifier(settings.database_name), sql.Identifier(settings.role_name)
            ).as_string()
        )

        for name in settings.odoo_database_names:
            if not self._admin_exists(
                f"SELECT 1 FROM pg_database WHERE datname = "
                f"{sql.Literal(name).as_string()}"
            ):
                raise BootstrapError(f"Configured Odoo database does not exist: {name}")

        runtime_url = _runtime_url(settings, self._password)
        try:
            self._verify_runtime_connection(runtime_url)
        except BootstrapError:
            if role_created:
                raise
            self._admin_execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(settings.role_name), sql.Literal(self._password)
                ).as_string()
            )
            self._verify_runtime_connection(runtime_url)
        hba_changed = self._ensure_hba_isolation()
        self._verify_isolation(runtime_url)
        self._verify_odoo_access()
        backup_path = self._backup_before_pending_upgrade(runtime_url)
        self._run_migrations(runtime_url)
        return PostgresBootstrapResult(
            mode=settings.mode,
            database_created=database_created,
            role_created=role_created,
            hba_changed=hba_changed,
            isolation_verified=True,
            migrations_applied=True,
            runtime_url=runtime_url,
            backup_path=backup_path,
        )

    def _psql_command(self) -> list[str]:
        return [
            *self._command_prefix,
            str(self._settings.psql_path),
            "-X",
            "--no-psqlrc",
            "--set",
            "ON_ERROR_STOP=1",
            "--quiet",
            "--tuples-only",
            "--no-align",
            "--dbname",
            "postgres",
            "--host",
            self._settings.admin_host,
            "--port",
            str(self._settings.port),
        ]

    def _admin_scalar(self, statement: str) -> str:
        completed = subprocess.run(
            self._psql_command(),
            input=f"{statement};\n",
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise BootstrapError("PostgreSQL administrative command failed")
        return completed.stdout.strip()

    def _admin_exists(self, statement: str) -> bool:
        return self._admin_scalar(statement) == "1"

    def _admin_execute(self, statement: str) -> None:
        self._admin_scalar(statement)

    def _ensure_hba_isolation(self) -> bool:
        hba_path = Path(self._admin_scalar("SHOW hba_file"))
        try:
            current = hba_path.read_text(encoding="utf-8")
            metadata = hba_path.stat()
        except OSError as error:
            raise BootstrapError("Cannot read PostgreSQL hba_file for targeted isolation") from error
        if not stat.S_ISREG(metadata.st_mode):
            raise BootstrapError("PostgreSQL hba_file must be a regular file")

        managed_lines = [_HBA_BEGIN]
        for database in self._settings.odoo_database_names:
            managed_lines.extend(
                (
                    f"local {database} {self._settings.role_name} reject",
                    f"host {database} {self._settings.role_name} 0.0.0.0/0 reject",
                    f"host {database} {self._settings.role_name} ::0/0 reject",
                )
            )
        managed_lines.append(_HBA_END)
        managed_block = "\n".join(managed_lines)

        begin = current.find(_HBA_BEGIN)
        end = current.find(_HBA_END)
        if (begin == -1) != (end == -1) or (begin != -1 and end < begin):
            raise BootstrapError("PostgreSQL hba_file contains a malformed managed block")
        if begin == -1:
            updated = f"{managed_block}\n{current.lstrip()}"
        else:
            end += len(_HBA_END)
            updated = f"{current[:begin]}{managed_block}{current[end:]}"
        if updated == current:
            return False

        descriptor, temporary_name = tempfile.mkstemp(dir=hba_path.parent, prefix=".pg_hba.conf.")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.replace(temporary_name, hba_path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        if self._admin_scalar("SELECT pg_reload_conf()") != "t":
            raise BootstrapError("PostgreSQL rejected configuration reload")
        if self._admin_scalar(
            "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL"
        ) != "0":
            raise BootstrapError("PostgreSQL reports an invalid pg_hba.conf rule")
        return True

    @staticmethod
    def _verify_runtime_connection(runtime_url: str) -> None:
        try:
            with (
                psycopg.connect(
                    _psycopg_url(runtime_url), connect_timeout=5
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT current_database(), current_user")
                cursor.fetchone()
        except psycopg.Error as error:
            raise BootstrapError("Assistant role cannot connect to the Assistant database") from error

    def _verify_isolation(self, runtime_url: str) -> None:
        for database in self._settings.odoo_database_names:
            target = _psycopg_url(runtime_url, database=database)
            try:
                with psycopg.connect(target, connect_timeout=5):
                    pass
            except psycopg.Error:
                continue
            raise BootstrapError("Assistant role unexpectedly connected to an Odoo database")

    def _verify_odoo_access(self) -> None:
        if not self._settings.odoo_os_user:
            raise BootstrapError(
                "Managed mode needs the Odoo OS user to verify legitimate database access"
            )
        for database in self._settings.odoo_database_names:
            current_user = pwd.getpwuid(os.geteuid()).pw_name
            user_prefix = (
                []
                if current_user == self._settings.odoo_os_user
                else ["runuser", "--user", self._settings.odoo_os_user, "--"]
            )
            command = [
                *user_prefix,
                str(self._settings.psql_path),
                "-X",
                "--no-psqlrc",
                "--set",
                "ON_ERROR_STOP=1",
                "--quiet",
                "--dbname",
                database,
                "--host",
                self._settings.admin_host,
                "--port",
                str(self._settings.port),
                "--command",
                "SELECT 1",
            ]
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise BootstrapError(
                    "Odoo database access probe failed; supply a deployment where the Odoo "
                    "service user can authenticate locally before changing isolation"
                )

    def _run_migrations(self, runtime_url: str) -> None:
        environment = os.environ.copy()
        environment["ODOO_AI_DATABASE_URL"] = runtime_url
        environment["ODOO_AI_DATABASE_NAME"] = self._settings.database_name
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(self._settings.alembic_config),
                "upgrade",
                "head",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if completed.returncode != 0:
            sanitized = completed.stderr.replace(runtime_url, "<redacted-database-url>")
            if self._password:
                sanitized = sanitized.replace(self._password, "<redacted-password>")
            detail = " | ".join(sanitized.strip().splitlines()[-3:])[:600]
            suffix = f": {detail}" if detail else ""
            raise BootstrapError(f"Assistant database migrations failed{suffix}")

    def _backup_before_pending_upgrade(self, runtime_url: str) -> str | None:
        try:
            with (
                psycopg.connect(
                    _psycopg_url(runtime_url), connect_timeout=5
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT to_regclass('public.alembic_version')")
                if cursor.fetchone()[0] is None:
                    return None
                cursor.execute("SELECT version_num FROM alembic_version")
                row = cursor.fetchone()
                current = str(row[0]) if row else None
        except psycopg.Error as error:
            raise BootstrapError("Cannot inspect Assistant migration revision") from error

        expected = ScriptDirectory.from_config(
            Config(self._settings.alembic_config)
        ).get_current_head()
        if current is None or current == expected:
            return None
        if self._settings.backup_dir is None:
            raise BootstrapError(
                "Pending Assistant migrations require --assistant-backup-dir for a pre-upgrade backup"
            )
        return str(self._create_backup(runtime_url, current_revision=current))

    def _create_backup(self, runtime_url: str, *, current_revision: str) -> Path:
        backup_dir = self._settings.backup_dir
        assert backup_dir is not None
        try:
            backup_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            metadata = backup_dir.lstat()
        except OSError as error:
            raise BootstrapError("Cannot prepare Assistant database backup directory") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise BootstrapError("Assistant database backup path must be a directory")
        os.chmod(backup_dir, 0o700)

        safe_revision = re.sub(r"[^A-Za-z0-9_.-]", "_", current_revision)[:80]
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = backup_dir / (
            f"{self._settings.database_name}-{timestamp}-from-{safe_revision}.dump"
        )
        descriptor, temporary_name = tempfile.mkstemp(dir=backup_dir, prefix=".assistant-db-")
        os.close(descriptor)
        temporary = Path(temporary_name)
        parsed = make_url(runtime_url)
        environment = os.environ.copy()
        if parsed.host:
            environment["PGHOST"] = parsed.host
        if parsed.port:
            environment["PGPORT"] = str(parsed.port)
        if parsed.username:
            environment["PGUSER"] = parsed.username
        if parsed.password:
            environment["PGPASSWORD"] = parsed.password
        environment["PGDATABASE"] = parsed.database or self._settings.database_name
        if sslmode := parsed.query.get("sslmode"):
            environment["PGSSLMODE"] = str(sslmode)
        try:
            completed = subprocess.run(
                [
                    str(self._settings.pg_dump_path),
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(temporary),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            if completed.returncode != 0 or temporary.stat().st_size == 0:
                raise BootstrapError("Assistant database pre-upgrade backup failed")
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
