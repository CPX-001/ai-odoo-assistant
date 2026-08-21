"""Idempotent privileged preparation of Assistant host resources."""

import grp
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
    odoo_config: str
    addons_paths: tuple[str, ...]
    odoo_service: str | None
    odoo_user: str
    user_created: bool
    group_created: bool
    odoo_reader_added: bool
    directories_created: tuple[str, ...]
    config_changed: bool
    secret_created: bool


def _generate_secret() -> str:
    return secrets.token_urlsafe(48)


class Bootstrapper:
    """Create only the non-DB, non-systemd foundation authorized by M1-05."""

    def __init__(
        self,
        *,
        paths: BootstrapPaths,
        account_manager: AccountManager,
        service_user: str = "odoo-ai",
        service_group: str = "odoo-ai",
        privileged_uid: int = 0,
        secret_factory: Callable[[], str] = _generate_secret,
    ) -> None:
        self._paths = paths
        self._account_manager = account_manager
        self._service_user = service_user
        self._service_group = service_group
        self._privileged_uid = privileged_uid
        self._secret_factory = secret_factory

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

        config_changed = self._ensure_config(accounts)
        secret_created = self._ensure_secret(accounts)
        return BootstrapResult(
            host=f"{host.distribution_id}:{host.version_id}",
            odoo_config=str(deployment.config_path),
            addons_paths=tuple(str(path) for path in deployment.addons_paths),
            odoo_service=odoo_service.unit,
            odoo_user=odoo_service.user,
            user_created=accounts.user_created,
            group_created=accounts.group_created,
            odoo_reader_added=accounts.reader_added,
            directories_created=tuple(created),
            config_changed=config_changed,
            secret_created=secret_created,
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

    def _service_config_content(self) -> str:
        values = {
            "ODOO_AI_HOST": "127.0.0.1",
            "ODOO_AI_PORT": "8000",
            "ODOO_AI_DATABASE_NAME": "odoo_ai",
            "ODOO_AI_ALEMBIC_CONFIG": str(self._paths.install_dir / "alembic.ini"),
            "ODOO_AI_SHARED_SECRET_FILE": str(self._paths.shared_secret),
        }
        for value in values.values():
            if any(character.isspace() for character in value):
                raise BootstrapError("Bootstrap paths and config values cannot contain whitespace")
        return "".join(f"{key}={value}\n" for key, value in values.items())

    def _ensure_config(self, accounts: AccountState) -> bool:
        path = self._paths.service_config
        content = self._service_config_content()
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
