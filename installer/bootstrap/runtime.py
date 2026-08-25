"""Atomic, versioned installation of the Assistant runtime payload."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import tomllib

from installer.bootstrap.bootstrap import BootstrapError

_RELEASE_PART = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True, slots=True)
class RuntimeInstallSettings:
    source_root: Path
    install_dir: Path
    python_executable: Path = Path(sys.executable)


@dataclass(frozen=True, slots=True)
class RuntimeInstallResult:
    version: str
    build_id: str
    release_dir: str
    release_created: bool
    current_changed: bool
    previous_release: str | None


class RuntimeCommandRunner(Protocol):
    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]: ...


class SubprocessRuntimeRunner:
    def run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(arguments, check=False, capture_output=True, text=True)


class RuntimeInstaller:
    """Install a complete release before atomically activating it."""

    def __init__(
        self,
        *,
        settings: RuntimeInstallSettings,
        runner: RuntimeCommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner or SubprocessRuntimeRunner()

    def ensure(self) -> RuntimeInstallResult:
        source = self._settings.source_root.resolve()
        pyproject = source / "service/pyproject.toml"
        migrations = source / "migrations"
        alembic_config = source / "alembic.ini"
        if not pyproject.is_file() or not migrations.is_dir() or not alembic_config.is_file():
            raise BootstrapError("Runtime source does not contain service, migrations, and Alembic")
        version = self._read_version(pyproject)
        build_id = self._fingerprint(source)
        release_name = f"{_RELEASE_PART.sub('_', version)}-{build_id}"
        releases_dir = self._settings.install_dir / "releases"
        releases_dir.mkdir(parents=True, exist_ok=True)
        release_dir = releases_dir / release_name
        release_created = False
        if not release_dir.exists():
            self._create_release(source, release_dir)
            release_created = True
        elif not self._valid_release(release_dir):
            raise BootstrapError("Existing Assistant runtime release is incomplete")

        current = self._settings.install_dir / "current"
        previous_target = self._symlink_target(current)
        current_changed = previous_target != release_dir
        if current_changed:
            if previous_target is not None:
                self._replace_symlink(
                    self._settings.install_dir / "previous", previous_target
                )
            self._replace_symlink(current, release_dir)
        return RuntimeInstallResult(
            version=version,
            build_id=build_id,
            release_dir=str(release_dir),
            release_created=release_created,
            current_changed=current_changed,
            previous_release=str(previous_target) if previous_target else None,
        )

    def activate_previous(self, *, schema_compatible: bool) -> str:
        """Swap current/previous only after an explicit schema-compatibility decision."""

        if not schema_compatible:
            raise BootstrapError(
                "Runtime rollback requires explicit schema compatibility acknowledgement"
            )
        current = self._settings.install_dir / "current"
        previous = self._settings.install_dir / "previous"
        current_target = self._symlink_target(current)
        previous_target = self._symlink_target(previous)
        if current_target is None or previous_target is None:
            raise BootstrapError("Runtime rollback requires current and previous releases")
        if not self._valid_release(previous_target):
            raise BootstrapError("Previous Assistant runtime release is incomplete")
        self._replace_symlink(previous, current_target)
        self._replace_symlink(current, previous_target)
        return str(previous_target)

    @staticmethod
    def _read_version(pyproject: Path) -> str:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            version = str(data["project"]["version"])
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
            raise BootstrapError("Cannot read Assistant runtime version") from error
        if not version or len(version) > 80:
            raise BootstrapError("Assistant runtime version is invalid")
        return version

    @staticmethod
    def _fingerprint(source: Path) -> str:
        digest = hashlib.sha256()
        roots = (
            source / "service/pyproject.toml",
            source / "service/src",
            source / "migrations",
            source / "alembic.ini",
        )
        files: list[Path] = []
        for root in roots:
            if root.is_file():
                files.append(root)
            else:
                files.extend(
                    path
                    for path in root.rglob("*")
                    if path.is_file()
                    and "__pycache__" not in path.parts
                    and not path.name.endswith((".pyc", ".pyo"))
                )
        for path in sorted(files):
            digest.update(str(path.relative_to(source)).encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()[:16]

    def _create_release(self, source: Path, destination: Path) -> None:
        temporary = Path(
            tempfile.mkdtemp(
                dir=destination.parent, prefix=f".{destination.name}.installing."
            )
        )
        try:
            shutil.copytree(
                source / "service",
                temporary / "service",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.egg-info"),
            )
            shutil.copytree(
                source / "migrations",
                temporary / "migrations",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            shutil.copy2(source / "alembic.ini", temporary / "alembic.ini")
            self._run(
                [str(self._settings.python_executable), "-m", "venv", str(temporary / ".venv")],
                "create Assistant runtime virtual environment",
            )
            self._run(
                [
                    str(temporary / ".venv/bin/python"),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    str(temporary / "service"),
                ],
                "install Assistant runtime package",
            )
            self._install_relocatable_launcher(temporary)
            if not self._valid_release(temporary):
                raise BootstrapError("Installed Assistant runtime release is incomplete")
            temporary.chmod(0o755)
            os.replace(temporary, destination)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def _run(self, arguments: list[str], action: str) -> None:
        if self._runner.run(arguments).returncode != 0:
            raise BootstrapError(f"Failed to {action}")

    @staticmethod
    def _install_relocatable_launcher(release: Path) -> None:
        """Replace pip's absolute shebang with a launcher safe after atomic rename."""

        launcher = release / ".venv/bin/odoo-ai-service"
        launcher.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            'script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
            'exec "$script_dir/python" -m odoo_ai.api "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)

    @staticmethod
    def _valid_release(path: Path) -> bool:
        return all(
            candidate.is_file()
            for candidate in (
                path / "alembic.ini",
                path / ".venv/bin/python",
                path / ".venv/bin/odoo-ai-service",
            )
        ) and (path / "migrations").is_dir()

    @staticmethod
    def _symlink_target(path: Path) -> Path | None:
        try:
            if not path.is_symlink():
                if path.exists():
                    raise BootstrapError("Runtime activation path must be a symlink")
                return None
            raw_target = Path(os.readlink(path))
        except OSError as error:
            raise BootstrapError("Cannot inspect Assistant runtime activation") from error
        return (path.parent / raw_target).resolve() if not raw_target.is_absolute() else raw_target

    @staticmethod
    def _replace_symlink(path: Path, target: Path) -> None:
        temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
        temporary.unlink(missing_ok=True)
        try:
            os.symlink(os.path.relpath(target, path.parent), temporary)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
