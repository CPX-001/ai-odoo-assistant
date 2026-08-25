"""Codex executable discovery for the Odoo-owned Assistant runtime."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CodexStatus:
    configured: str | None
    executable: Path | None
    state: str

    @property
    def ready(self) -> bool:
        return self.state == "ready" and self.executable is not None


def detect_codex(configured: str | None = None) -> CodexStatus:
    """Resolve Codex without shell execution, downloads, or host mutation."""

    requested = (configured or "").strip() or None
    candidate: str | None
    if requested:
        expanded = os.path.expanduser(requested)
        if os.path.sep in expanded:
            path = Path(expanded)
            if not path.is_absolute():
                return CodexStatus(requested, None, "configured_path_not_absolute")
            candidate = str(path)
        else:
            candidate = shutil.which(expanded)
            if candidate is None:
                return CodexStatus(requested, None, "not_found")
    else:
        candidate = shutil.which("codex")
        if candidate is None:
            return CodexStatus(None, None, "not_found")

    path = Path(candidate).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return CodexStatus(requested, None, "not_found")
    if not resolved.is_file():
        return CodexStatus(requested, None, "not_a_file")
    if not os.access(resolved, os.X_OK):
        return CodexStatus(requested, resolved, "not_executable")
    return CodexStatus(requested, resolved, "ready")
