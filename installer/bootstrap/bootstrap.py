"""Idempotent privileged preparation of Assistant host resources."""

import grp
import json
import os
import pwd
import secrets
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from installer.bootstrap.discovery import LinuxHost, OdooDeployment, OdooService


class BootstrapError(RuntimeError):
    """Raised when bootstrap cannot safely create or reuse a host resource."""


@dataclass(frozen=True, slots=True)
class BootstrapPaths:
    install_dir: Path
    config_dir: Path
    state_dir: Path
    runtime_dir: Path

    @property
    def service_config(self) -> Path:
        return self.config_dir / "service.env"

    @property
    def shared_secret(self) -> Path:
        return self.config_dir / "shared-secret"

    @property
    def database_password(self) -> Path:
        return self.config_dir / "database-password"


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Customer-adjustable runtime settings that are safe to persist outside code."""

    host: str = "127.0.0.1"
    port: int = 8000
    database_name: str = "odoo_ai"
    database_url: str | None = None
    alembic_config: Path | None = None


@dataclass(frozen=True, slots=True)
class AccountState:
    uid: int
    gid: int
    user_created: bool
    group_created: bool
    reader_added: bool


class AccountManager(Protocol):
    def ensure(
        self, *, user: str, group: str, home: Path, shared_reader_user: str
    ) -> AccountState: ...


class DatabaseManager(Protocol):
    def ensure(self) -> object: ...


class SystemdManager(Protocol):
    def ensure(self, *, config_changed: bool = False) -> object: ...


class RuntimeManager(Protocol):
    def ensure(self) -> object: ...


class SystemAccountManager:
    """Create a locked service account and scoped shared-reader membership."""

    @staticmethod
    def _run(arguments: list[str]) -> None:
        completed = subprocess.run(arguments, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise BootstrapError(f"Host account command failed: {arguments[0]}")

    def ensure(self, *, user: str, group: str, home: Path, shared_reader_user: str) -> AccountState:
        group_created = False
        try:
            group_record = grp.getgrnam(group)
        except KeyError:
            self._run(["groupadd", "--system", group])
            group_record = grp.getgrnam(group)
            group_created = True

        user_created = False
        try:
            user_record = pwd.getpwnam(user)
        except KeyError:
            self._run(
                [
                    "useradd",
                    "--system",
                    "--gid",
                    group,
                    "--home-dir",
                    str(home),
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    user,
                ]
            )
            user_record = pwd.getpwnam(user)
            user_created = True

        valid_nologin_shells = {"/usr/sbin/nologin", "/sbin/nologin"}
        if (
            user_record.pw_uid == 0
            or user_record.pw_gid != group_record.gr_gid
            or Path(user_record.pw_dir) != home
            or user_record.pw_shell not in valid_nologin_shells
        ):
            raise BootstrapError(
                "Existing Assistant service account has unsafe identity or ownership"
            )
        try:
            reader_record = pwd.getpwnam(shared_reader_user)
        except KeyError as error:
            raise BootstrapError("Detected Odoo service user does not exist") from error
        if reader_record.pw_uid == 0:
            raise BootstrapError("Odoo service user must not be root")

        reader_groups = os.getgrouplist(shared_reader_user, reader_record.pw_gid)
        reader_added = group_record.gr_gid not in reader_groups
        if reader_added:
            self._run(["usermod", "--append", "--groups", group, shared_reader_user])

        return AccountState(
            uid=user_record.pw_uid,
            gid=group_record.gr_gid,
            user_created=user_created,
            group_created=group_created,
            reader_added=reader_added,
        )


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    host: str
    odoo_config: str | None
    addons_paths: tuple[str, ...]
    odoo_data_dir: str | None
    odoo_log_file: str | None
    odoo_service: str | None
    odoo_user: str
    user_created: bool
    group_created: bool
    odoo_reader_added: bool
    directories_created: tuple[str, ...]
    config_changed: bool
    secret_created: bool
    database_password_created: bool
    postgres_mode: str | None
    database_created: bool
    database_role_created: bool
    postgres_hba_changed: bool
    postgres_isolation_verified: bool
    migrations_applied: bool
    database_backup: str | None
    systemd_unit: str | None
    systemd_unit_changed: bool
    systemd_unit_enabled: bool
    service_restarted: bool
    service_active: bool
    loopback_verified: bool
    health_verified: bool
    admin_status_verified: bool
    runtime_version: str | None
    runtime_build_id: str | None
    runtime_release_created: bool
    runtime_current_changed: bool
    previous_runtime_release: str | None


def _generate_secret() -> str:
    return secrets.token_urlsafe(48)


def _quote_env_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise BootstrapError("Bootstrap config values cannot contain newlines")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class Bootstrapper:
    """Create only the non-DB, non-systemd foundation authorized by M1-05."""

    def __init__(
        self,
        *,
        paths: BootstrapPaths,
        account_manager: AccountManager,
        service_user: str = "odoo-ai",
        service_group: str = "odoo-ai",
        service_settings: ServiceSettings | None = None,
        privileged_uid: int = 0,
        secret_factory: Callable[[], str] = _generate_secret,
        database_manager: DatabaseManager | None = None,
        database_manager_factory: Callable[[str], DatabaseManager] | None = None,
        systemd_manager: SystemdManager | None = None,
        runtime_manager: RuntimeManager | None = None,
    ) -> None:
        self._paths = paths
        self._account_manager = account_manager
        self._service_user = service_user
        self._service_group = service_group
        self._service_settings = service_settings or ServiceSettings()
        self._privileged_uid = privileged_uid
        self._secret_factory = secret_factory
        self._database_manager = database_manager
        self._database_manager_factory = database_manager_factory
        self._systemd_manager = systemd_manager
        self._runtime_manager = runtime_manager

    def run(
        self, *, host: LinuxHost, deployment: OdooDeployment, odoo_service: OdooService
    ) -> BootstrapResult:
        accounts = self._account_manager.ensure(
            user=self._service_user,
            group=self._service_group,
            home=self._paths.state_dir,
            shared_reader_user=odoo_service.user,
        )

        created: list[str] = []
        directory_specs = (
            (self._paths.install_dir, 0o755, self._privileged_uid),
            (self._paths.config_dir, 0o750, self._privileged_uid),
            (self._paths.state_dir, 0o750, accounts.uid),
            (self._paths.runtime_dir, 0o750, accounts.uid),
        )
        for path, mode, uid in directory_specs:
            if self._ensure_directory(path, mode=mode, uid=uid, gid=accounts.gid):
                created.append(str(path))

        secret_created = self._ensure_secret(accounts)
        runtime_result = self._runtime_manager.ensure() if self._runtime_manager else None
        database_password_created = False
        postgres_result = None
        database_manager = self._database_manager
        if self._database_manager_factory is not None:
            password, database_password_created = self._ensure_database_password(accounts)
            database_manager = self._database_manager_factory(password)
        if database_manager is not None:
            postgres_result = database_manager.ensure()
            self._service_settings = ServiceSettings(
                host=self._service_settings.host,
                port=self._service_settings.port,
                database_name=self._service_settings.database_name,
                database_url=postgres_result.runtime_url,
                alembic_config=self._service_settings.alembic_config,
            )
        config_changed = self._ensure_config(
            accounts,
            source_roots=deployment.addons_paths,
            log_file=deployment.log_file,
        )
        systemd_result = (
            self._systemd_manager.ensure(
                config_changed=(
                    config_changed
                    or bool(runtime_result and runtime_result.current_changed)
                )
            )
            if self._systemd_manager
            else None
        )
        return BootstrapResult(
            host=f"{host.distribution_id}:{host.version_id}",
            odoo_config=str(deployment.config_path) if deployment.config_path else None,
            addons_paths=tuple(str(path) for path in deployment.addons_paths),
            odoo_data_dir=str(deployment.data_dir) if deployment.data_dir else None,
            odoo_log_file=str(deployment.log_file) if deployment.log_file else None,
            odoo_service=odoo_service.unit,
            odoo_user=odoo_service.user,
            user_created=accounts.user_created,
            group_created=accounts.group_created,
            odoo_reader_added=accounts.reader_added,
            directories_created=tuple(created),
            config_changed=config_changed,
            secret_created=secret_created,
            database_password_created=database_password_created,
            postgres_mode=postgres_result.mode if postgres_result else None,
            database_created=postgres_result.database_created if postgres_result else False,
            database_role_created=postgres_result.role_created if postgres_result else False,
            postgres_hba_changed=postgres_result.hba_changed if postgres_result else False,
            postgres_isolation_verified=(
                postgres_result.isolation_verified if postgres_result else False
            ),
            migrations_applied=postgres_result.migrations_applied if postgres_result else False,
            database_backup=postgres_result.backup_path if postgres_result else None,
            systemd_unit=systemd_result.unit_name if systemd_result else None,
            systemd_unit_changed=systemd_result.unit_changed if systemd_result else False,
            systemd_unit_enabled=systemd_result.unit_enabled if systemd_result else False,
            service_restarted=systemd_result.service_restarted if systemd_result else False,
            service_active=systemd_result.service_active if systemd_result else False,
            loopback_verified=systemd_result.loopback_verified if systemd_result else False,
            health_verified=systemd_result.health_verified if systemd_result else False,
            admin_status_verified=(
                systemd_result.admin_status_verified if systemd_result else False
            ),
            runtime_version=runtime_result.version if runtime_result else None,
            runtime_build_id=runtime_result.build_id if runtime_result else None,
            runtime_release_created=(
                runtime_result.release_created if runtime_result else False
            ),
            runtime_current_changed=(
                runtime_result.current_changed if runtime_result else False
            ),
            previous_runtime_release=(
                runtime_result.previous_release if runtime_result else None
            ),
        )

    @staticmethod
    def _validate_regular_file(path: Path) -> os.stat_result | None:
        try:
            result = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(result.st_mode):
            raise BootstrapError(f"Refusing non-regular bootstrap file: {path}")
        return result

    @staticmethod
    def _ensure_directory(path: Path, *, mode: int, uid: int, gid: int) -> bool:
        created = False
        try:
            current = path.lstat()
            if not stat.S_ISDIR(current.st_mode):
                raise BootstrapError(f"Refusing non-directory bootstrap path: {path}")
        except FileNotFoundError:
            path.mkdir(parents=True, mode=mode)
            created = True
        os.chmod(path, mode)
        os.chown(path, uid, gid)
        return created

    def _service_config_content(
        self,
        *,
        source_roots: tuple[Path, ...] = (),
        log_file: Path | None = None,
    ) -> str:
        settings = self._service_settings
        if settings.host not in {"127.0.0.1", "::1", "localhost"}:
            raise BootstrapError("MVP Assistant Service host must remain loopback")
        if not 1 <= settings.port <= 65535:
            raise BootstrapError("Assistant Service port must be between 1 and 65535")
        if not settings.database_name or any(
            character in settings.database_name for character in "\r\n="
        ):
            raise BootstrapError("Assistant database name is invalid")

        alembic_config = settings.alembic_config or self._paths.install_dir / "alembic.ini"
        values = {
            "ODOO_AI_HOST": settings.host,
            "ODOO_AI_PORT": str(settings.port),
            "ODOO_AI_DATABASE_NAME": settings.database_name,
            "ODOO_AI_ALEMBIC_CONFIG": str(alembic_config),
            "ODOO_AI_SHARED_SECRET_FILE": str(self._paths.shared_secret),
            "ODOO_AI_SOURCE_ROOTS": json.dumps(
                [str(path) for path in source_roots], separators=(",", ":")
            ),
        }
        if settings.database_url is not None:
            values["ODOO_AI_DATABASE_URL"] = settings.database_url
        if log_file is not None:
            values["ODOO_AI_LOG_FILE"] = str(log_file)
        return "".join(f"{key}={_quote_env_value(value)}\n" for key, value in values.items())

    def _ensure_config(
        self,
        accounts: AccountState,
        *,
        source_roots: tuple[Path, ...] = (),
        log_file: Path | None = None,
    ) -> bool:
        path = self._paths.service_config
        content = self._service_config_content(
            source_roots=source_roots, log_file=log_file
        )
        existing = self._validate_regular_file(path)
        if existing is not None and path.read_text(encoding="utf-8") == content:
            os.chmod(path, 0o640)
            os.chown(path, self._privileged_uid, accounts.gid)
            return False

        file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".service.env.")
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o640)
                os.fchown(stream.fileno(), self._privileged_uid, accounts.gid)
            os.replace(temporary_name, path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        return True

    def _ensure_secret(self, accounts: AccountState) -> bool:
        path = self._paths.shared_secret
        existing = self._validate_regular_file(path)
        if existing is not None:
            if len(path.read_text(encoding="utf-8").strip()) < 43:
                raise BootstrapError("Existing shared secret is invalid; rotate it explicitly")
            os.chmod(path, 0o640)
            os.chown(path, self._privileged_uid, accounts.gid)
            return False

        secret = self._secret_factory()
        if len(secret) < 43 or "\n" in secret or "\r" in secret:
            raise BootstrapError("Generated shared secret does not meet policy")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{secret}\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o640)
            os.fchown(stream.fileno(), self._privileged_uid, accounts.gid)
        return True

    def _ensure_database_password(self, accounts: AccountState) -> tuple[str, bool]:
        path = self._paths.database_password
        existing = self._validate_regular_file(path)
        if existing is not None:
            password = path.read_text(encoding="utf-8").strip()
            if len(password) < 43:
                raise BootstrapError(
                    "Existing database password is invalid; rotate it explicitly"
                )
            os.chmod(path, 0o640)
            os.chown(path, self._privileged_uid, accounts.gid)
            return password, False

        password = self._secret_factory()
        if len(password) < 43 or "\n" in password or "\r" in password:
            raise BootstrapError("Generated database password does not meet policy")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{password}\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o640)
            os.fchown(stream.fileno(), self._privileged_uid, accounts.gid)
        return password, True
