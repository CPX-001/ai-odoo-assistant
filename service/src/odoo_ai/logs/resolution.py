"""Resolve one trusted file-log path without guessing the host layout."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from odoo_ai.contracts import LogCapabilityState

LOG_FILE_ENV = "ODOO_AI_LOG_FILE"


class LogFileOrigin(StrEnum):
    OVERRIDE = "override"
    CONFIG = "config"
    RUNTIME = "runtime"
    SUPERVISOR = "supervisor"
    HINT = "hint"


@dataclass(frozen=True, slots=True)
class LogFileSelection:
    override: tuple[str | Path, ...] = ()
    config: tuple[str | Path, ...] = ()
    runtime: tuple[str | Path, ...] = ()
    supervisor: tuple[str | Path, ...] = ()
    hints: tuple[str | Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedLogFile:
    path: Path
    origin: LogFileOrigin


@dataclass(frozen=True, slots=True)
class LogFileResolution:
    state: LogCapabilityState
    resolved: ResolvedLogFile | None
    code: str


LogFileProbe = Callable[[Path], LogCapabilityState | None]


def log_file_override_from_env(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    source = os.environ if environ is None else environ
    value = source.get(LOG_FILE_ENV, "")
    if not value:
        return ()
    if value != value.strip() or "\x00" in value or len(value) > 4096:
        raise ValueError("log file override is invalid")
    return (value,)


def resolve_log_file(
    selection: LogFileSelection,
    *,
    probe: LogFileProbe | None = None,
) -> LogFileResolution:
    selected_origin: LogFileOrigin | None = None
    candidates: tuple[str | Path, ...] = ()
    for origin, values in (
        (LogFileOrigin.OVERRIDE, selection.override),
        (LogFileOrigin.RUNTIME, selection.runtime),
        (LogFileOrigin.SUPERVISOR, selection.supervisor),
        (LogFileOrigin.CONFIG, selection.config),
        (LogFileOrigin.HINT, selection.hints),
    ):
        if values:
            selected_origin = origin
            candidates = values
            break
    if selected_origin is None:
        return LogFileResolution(LogCapabilityState.NOT_FOUND, None, "log_file_unknown")
    normalized: list[Path] = []
    for candidate in candidates:
        try:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                raise ValueError
            normalized.append(path)
        except (OSError, RuntimeError, TypeError, ValueError):
            return LogFileResolution(LogCapabilityState.ERROR, None, "invalid_log_file")
    deduplicated = tuple(dict.fromkeys(normalized))
    if len(deduplicated) != 1:
        return LogFileResolution(LogCapabilityState.ERROR, None, "ambiguous_log_file")
    path = deduplicated[0]
    state = (probe or _probe_log_file)(path)
    if state is not None:
        return LogFileResolution(state, None, state.value.casefold())
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return LogFileResolution(LogCapabilityState.ERROR, None, "log_file_resolution_error")
    return LogFileResolution(
        LogCapabilityState.OPERATIONAL,
        ResolvedLogFile(resolved, selected_origin),
        "operational",
    )


def _probe_log_file(path: Path) -> LogCapabilityState | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return LogCapabilityState.NOT_FOUND
    except PermissionError:
        return LogCapabilityState.NO_PERMISSION
    except OSError:
        return LogCapabilityState.ERROR
    if not stat.S_ISREG(metadata.st_mode):
        return LogCapabilityState.ERROR
    if not os.access(path, os.R_OK):
        return LogCapabilityState.NO_PERMISSION
    return None
