"""Odoo-owned filesystem layout for the embedded Assistant runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from odoo.tools import config


class RuntimePathError(RuntimeError):
    """Raised when Odoo's runtime directory cannot be used safely."""


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    codex_home: Path
    runtime: Path
    cache: Path
    source: Path

    @classmethod
    def from_odoo(cls) -> RuntimePaths:
        data_dir = _odoo_data_dir()
        root = data_dir / "odoo_ai_assistant"
        return cls(
            root=root,
            codex_home=_codex_home(root),
            runtime=root / "runtime",
            cache=root / "cache",
            source=root / "source",
        )

    def ensure(self) -> RuntimePaths:
        """Create the bounded mutable layout using the current Odoo OS identity."""

        for path in (self.root, self.runtime, self.cache, self.source):
            _ensure_directory(path)
        managed_codex_home = self.root / "codex"
        if self.codex_home == managed_codex_home:
            _ensure_directory(self.codex_home)
        else:
            _validate_host_codex_home(self.codex_home)
        return self

    def codex_environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ if base is None else base)
        env["CODEX_HOME"] = str(self.codex_home)
        return env


def _odoo_data_dir() -> Path:
    raw = config.get("data_dir")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimePathError("odoo_data_dir_unconfigured")
    data_dir = Path(raw).expanduser()
    if not data_dir.is_absolute():
        raise RuntimePathError("odoo_data_dir_not_absolute")
    try:
        return data_dir.resolve(strict=False)
    except OSError as error:
        raise RuntimePathError("odoo_data_dir_unresolvable") from error


def _codex_home(root: Path) -> Path:
    """Use the host's primary Codex session when CODEX_HOME is configured.

    CODEX_HOME is process/host configuration, never a database parameter. The
    data-dir location remains the backwards-compatible managed fallback.
    """

    configured = os.environ.get("CODEX_HOME", "").strip()
    if not configured:
        return root / "codex"
    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise RuntimePathError("codex_home_not_absolute")
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise RuntimePathError("codex_home_unavailable") from error


def _validate_host_codex_home(path: Path) -> None:
    try:
        if path.is_symlink() or not path.is_dir():
            raise RuntimePathError("codex_home_invalid")
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
            raise RuntimePathError("codex_home_unavailable")
    except RuntimePathError:
        raise
    except OSError as error:
        raise RuntimePathError("codex_home_unavailable") from error


def _ensure_directory(path: Path) -> None:
    try:
        if path.is_symlink():
            raise RuntimePathError("runtime_path_symlink")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise RuntimePathError("runtime_path_invalid")
        # Do not chmod pre-existing Odoo data_dir parents. Only tighten paths owned
        # by this addon; a failure is surfaced instead of silently widening access.
        path.chmod(0o700)
    except RuntimePathError:
        raise
    except OSError as error:
        raise RuntimePathError("runtime_path_unavailable") from error
