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
    def from_odoo(cls) -> "RuntimePaths":
        data_dir = _odoo_data_dir()
        root = data_dir / "odoo_ai_assistant"
        return cls(
            root=root,
            codex_home=root / "codex",
            runtime=root / "runtime",
            cache=root / "cache",
            source=root / "source",
        )

    def ensure(self) -> "RuntimePaths":
        """Create the bounded mutable layout using the current Odoo OS identity."""

        for path in (self.root, self.codex_home, self.runtime, self.cache, self.source):
            _ensure_directory(path)
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
