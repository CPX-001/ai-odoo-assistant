"""Idempotent systemd installation and runtime smoke checks."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from installer.bootstrap.bootstrap import BootstrapError

_SAFE_ACCOUNT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*[$]?$|^[A-Za-z0-9_.-]+$")
_SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@-]+\.service$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True, slots=True)
class SystemdSettings:
    unit_name: str
    unit_dir: Path
    template_path: Path
    service_user: str
    service_group: str
    working_directory: Path
    environment_file: Path
    shared_secret_file: Path
    executable: Path
    host: str
    port: int
    privileged_uid: int = 0
    privileged_gid: int = 0
    systemctl_path: Path = Path("/usr/bin/systemctl")
    ss_path: Path = Path("/usr/bin/ss")


@dataclass(frozen=True, slots=True)
class SystemdBootstrapResult:
    unit_name: str
    unit_changed: bool
    unit_enabled: bool
    service_restarted: bool
    service_active: bool
    loopback_verified: bool
    health_verified: bool
    admin_status_verified: bool


class CommandRunner(Protocol):
    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(arguments, check=False, capture_output=True, text=True)


def _escape_unit_path(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise BootstrapError("systemd unit values cannot contain control characters")
    safe = frozenset("/._-" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    return "".join(
        character
        if character in safe
        else "".join(f"\\x{byte:02x}" for byte in character.encode("utf-8"))
        for character in value
    )


class SystemdInstaller:
    """Install/update one Assistant unit without coupling to Odoo's supervisor."""

    def __init__(self, *, settings: SystemdSettings, runner: CommandRunner | None = None) -> None:
        self._settings = settings
        self._runner = runner or SubprocessRunner()

    def ensure(self) -> SystemdBootstrapResult:
        self._validate()
        content = self._render_unit()
        unit_path = self._settings.unit_dir / self._settings.unit_name
        changed = self._ensure_unit_file(unit_path, content)
        restarted = False
        if changed:
            self._systemctl("daemon-reload")

        enabled = self._systemctl_status("is-enabled", self._settings.unit_name)
        if not enabled:
            self._systemctl("enable", self._settings.unit_name)
            enabled = True

        active = self._systemctl_status("is-active", self._settings.unit_name)
        if active and changed:
            self._systemctl("restart", self._settings.unit_name)
            restarted = True
        elif not active:
            self._systemctl("start", self._settings.unit_name)
        if not self._systemctl_status("is-active", self._settings.unit_name):
            raise BootstrapError("Assistant systemd service did not become active")

        self._verify_effective_user()
        self._verify_loopback_socket()
        health, admin = self._verify_http_endpoints()
        return SystemdBootstrapResult(
            unit_name=self._settings.unit_name,
            unit_changed=changed,
            unit_enabled=enabled,
            service_restarted=restarted,
            service_active=True,
            loopback_verified=True,
            health_verified=health,
            admin_status_verified=admin,
        )

    def _validate(self) -> None:
        settings = self._settings
        if not _SAFE_UNIT.fullmatch(settings.unit_name) or "/" in settings.unit_name:
            raise BootstrapError("Assistant systemd unit name is invalid")
        if not _SAFE_ACCOUNT.fullmatch(settings.service_user) or settings.service_user == "root":
            raise BootstrapError("Assistant systemd service user must be a safe non-root account")
        if not _SAFE_ACCOUNT.fullmatch(settings.service_group):
            raise BootstrapError("Assistant systemd service group is invalid")
        if settings.host not in _LOOPBACK_HOSTS:
            raise BootstrapError("Assistant systemd runtime must remain on loopback")
        if not 1 <= settings.port <= 65535:
            raise BootstrapError("Assistant systemd runtime port is invalid")
        for path, label in (
            (settings.template_path, "systemd template"),
            (settings.environment_file, "service environment file"),
            (settings.shared_secret_file, "shared secret file"),
            (settings.executable, "service executable"),
        ):
            try:
                metadata = path.stat()
            except OSError as error:
                raise BootstrapError(f"Assistant {label} is missing") from error
            if not stat.S_ISREG(metadata.st_mode):
                raise BootstrapError(f"Assistant {label} must be a regular file")
        if not os.access(settings.executable, os.X_OK):
            raise BootstrapError("Assistant service executable is not executable")

    def _render_unit(self) -> str:
        try:
            template = self._settings.template_path.read_text(encoding="utf-8")
        except OSError as error:
            raise BootstrapError("Cannot read Assistant systemd template") from error
        replacements = {
            "@SERVICE_USER@": self._settings.service_user,
            "@SERVICE_GROUP@": self._settings.service_group,
            "@WORKING_DIRECTORY@": _escape_unit_path(str(self._settings.working_directory)),
            "@ENVIRONMENT_FILE@": _escape_unit_path(str(self._settings.environment_file)),
            "@SERVICE_EXECUTABLE@": _escape_unit_path(str(self._settings.executable)),
        }
        for marker, value in replacements.items():
            template = template.replace(marker, value)
        if re.search(r"@[A-Z_]+@", template):
            raise BootstrapError("Assistant systemd template contains unresolved placeholders")
        return template

    def _ensure_unit_file(self, path: Path, content: str) -> bool:
        try:
            current = path.lstat()
        except FileNotFoundError:
            current = None
        if current is not None:
            if not stat.S_ISREG(current.st_mode):
                raise BootstrapError("Refusing non-regular Assistant systemd unit path")
            if path.read_text(encoding="utf-8") == content:
                os.chmod(path, 0o644)
                os.chown(path, self._settings.privileged_uid, self._settings.privileged_gid)
                return False
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".assistant-unit.")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o644)
                os.fchown(
                    stream.fileno(),
                    self._settings.privileged_uid,
                    self._settings.privileged_gid,
                )
            os.replace(temporary_name, path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        return True

    def _systemctl(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = self._runner.run([str(self._settings.systemctl_path), *arguments])
        if completed.returncode != 0:
            raise BootstrapError(f"systemctl {arguments[0]} failed for Assistant service")
        return completed

    def _systemctl_status(self, action: str, unit: str) -> bool:
        return self._runner.run(
            [str(self._settings.systemctl_path), action, "--quiet", unit]
        ).returncode == 0

    def _verify_effective_user(self) -> None:
        completed = self._systemctl(
            "show", self._settings.unit_name, "--property=User", "--value", "--no-pager"
        )
        if completed.stdout.strip() != self._settings.service_user:
            raise BootstrapError("Assistant service effective user does not match configuration")

    def _verify_loopback_socket(self) -> None:
        deadline = time.monotonic() + 5
        completed = None
        while time.monotonic() < deadline:
            completed = self._runner.run(
                [
                    str(self._settings.ss_path),
                    "-H",
                    "-ltn",
                    f"sport = :{self._settings.port}",
                ]
            )
            if completed.returncode == 0 and completed.stdout.strip():
                break
            time.sleep(0.1)
        if completed is None or completed.returncode != 0 or not completed.stdout.strip():
            raise BootstrapError("Assistant service is not listening on its configured port")
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            address = fields[3]
            if not (
                address.startswith("127.")
                or address.startswith("[::1]:")
                or address.startswith("::1:")
            ):
                raise BootstrapError("Assistant service is listening outside loopback")

    def _verify_http_endpoints(self) -> tuple[bool, bool]:
        host = "127.0.0.1" if self._settings.host == "localhost" else self._settings.host
        display_host = f"[{host}]" if ":" in host else host
        results: list[bool] = []
        try:
            shared_secret = self._settings.shared_secret_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise BootstrapError("Assistant shared secret is unavailable for runtime smoke") from error
        if len(shared_secret) < 43:
            raise BootstrapError("Assistant shared secret is invalid for runtime smoke")
        for path, expected_status in (("/health", "ok"), ("/v1/admin/status", None)):
            deadline = time.monotonic() + 5
            last_error: Exception | None = None
            while time.monotonic() < deadline:
                try:
                    request = urllib.request.Request(
                        f"http://{display_host}:{self._settings.port}{path}"
                    )
                    if path == "/v1/admin/status":
                        request.add_header("X-Odoo-AI-Shared-Secret", shared_secret)
                    with urllib.request.urlopen(request, timeout=1) as response:
                        payload = json.loads(response.read())
                    break
                except (OSError, ValueError, urllib.error.URLError) as error:
                    last_error = error
                    time.sleep(0.1)
            else:
                raise BootstrapError(f"Assistant runtime smoke failed for {path}") from last_error
            results.append(response.status == 200 and (expected_status is None or payload.get("status") == expected_status))
        if not all(results):
            raise BootstrapError("Assistant runtime returned an invalid smoke response")
        return results[0], results[1]
