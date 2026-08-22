"""Safe source-root resolution and bounded incremental scan orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from odoo_ai.contracts import (
    SourceCapabilityState,
    SourceFileKind,
    SourceProvenance,
)

SOURCE_ROOTS_ENV = "ODOO_AI_SOURCE_ROOTS"
_MODULE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class RootOrigin(StrEnum):
    OVERRIDE = "override"
    RUNTIME = "runtime"
    SUPERVISOR = "supervisor"
    CONFIG = "config"
    HINT = "hint"


@dataclass(frozen=True, slots=True)
class RootSelection:
    override: tuple[str | Path, ...] = ()
    runtime: tuple[str | Path, ...] = ()
    supervisor: tuple[str | Path, ...] = ()
    config: tuple[str | Path, ...] = ()
    hints: tuple[str | Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedSourceRoot:
    path: Path
    origin: RootOrigin


@dataclass(frozen=True, slots=True)
class RootIssue:
    origin: RootOrigin
    state: SourceCapabilityState
    code: str


@dataclass(frozen=True, slots=True)
class RootResolution:
    roots: tuple[ResolvedSourceRoot, ...]
    issues: tuple[RootIssue, ...]
    selected_origin: RootOrigin | None


@dataclass(frozen=True, slots=True)
class ModuleSource:
    name: str
    root: ResolvedSourceRoot
    path: Path
    provenance: SourceProvenance = SourceProvenance.UNKNOWN


@dataclass(frozen=True, slots=True)
class ModuleInventory:
    modules: tuple[ModuleSource, ...]
    missing: tuple[str, ...]
    issues: tuple[ScanError, ...]


@dataclass(frozen=True, slots=True)
class ExtractedSymbol:
    kind: str
    model: str | None
    name: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class ExtractedXmlRecord:
    xml_id: str
    model: str | None
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class FileExtraction:
    symbols: tuple[ExtractedSymbol, ...] = ()
    xml_records: tuple[ExtractedXmlRecord, ...] = ()
    metadata: dict[str, JsonValue] | None = None


class SourceExtractionError(ValueError):
    """Sanitized parser failure isolated to one source file."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FileScanContext:
    module: str
    logical_path: str
    kind: SourceFileKind
    fingerprint: str
    size_bytes: int
    mtime_ns: int
    content: bytes


class SourceExtractor(Protocol):
    def extract(self, context: FileScanContext) -> FileExtraction: ...


class NoopExtractor:
    """Explicit M3 stub for a known source kind with no extractor yet."""

    def extract(self, context: FileScanContext) -> FileExtraction:
        del context
        return FileExtraction()


@dataclass(frozen=True, slots=True)
class StoredSourceFile:
    file_id: UUID
    fingerprint_changed: bool


class SourceScanStore(Protocol):
    def open_scan(self, *, instance_profile_id: UUID) -> UUID: ...

    def upsert_file(
        self,
        *,
        scan_run_id: UUID,
        module: str,
        logical_path: str,
        kind: SourceFileKind,
        fingerprint: str,
        size_bytes: int,
        provenance: SourceProvenance,
    ) -> StoredSourceFile: ...

    def replace_derivatives(
        self,
        *,
        source_file_id: UUID,
        symbols: tuple[ExtractedSymbol, ...],
        xml_records: tuple[ExtractedXmlRecord, ...],
        metadata: Mapping[str, JsonValue] | None,
    ) -> None: ...

    def mark_stale(self, *, scan_run_id: UUID, seen_file_ids: set[UUID]) -> int: ...

    def finish_scan(
        self,
        *,
        scan_run_id: UUID,
        succeeded: bool,
        fingerprint: str | None,
        error_code: str | None,
    ) -> None: ...

    def record_capability(
        self, *, instance_profile_id: UUID, state: SourceCapabilityState
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ScanLimits:
    max_modules: int = 512
    max_files: int = 5000
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_seconds: float = 30.0
    max_depth: int = 32
    excluded_directories: frozenset[str] = frozenset(
        {".git", ".hg", ".svn", "__pycache__", "node_modules"}
    )

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_modules,
            self.max_files,
            self.max_file_bytes,
            self.max_total_bytes,
            self.max_depth,
        )
        if any(type(value) is not int or value <= 0 for value in integer_limits):
            raise ValueError("scan integer limits must be positive")
        if not isinstance(self.max_seconds, (int, float)) or self.max_seconds <= 0:
            raise ValueError("scan time limit must be positive")


@dataclass(frozen=True, slots=True)
class ScanError:
    code: str
    module: str | None = None
    logical_path: str | None = None


@dataclass(frozen=True, slots=True)
class SourceScanMetrics:
    modules: int = 0
    files_seen: int = 0
    files_extracted: int = 0
    files_unchanged: int = 0
    bytes_hashed: int = 0
    stale_files: int = 0


@dataclass(frozen=True, slots=True)
class SourceScanResult:
    capability: SourceCapabilityState
    scan_run_id: UUID | None
    fingerprint: str | None
    metrics: SourceScanMetrics
    errors: tuple[ScanError, ...]


RootProbe = Callable[[Path], SourceCapabilityState | None]


def source_root_overrides_from_env(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Load an administrator-managed JSON list without guessing host paths."""

    source = os.environ if environ is None else environ
    raw = source.get(SOURCE_ROOTS_ENV, "")
    if not raw:
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("source roots override must be a JSON list") from None
    if (
        not isinstance(values, list)
        or len(values) > 128
        or any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 4096
            for value in values
        )
    ):
        raise ValueError("source roots override must be a bounded JSON list")
    return tuple(values)


def resolve_source_roots(
    selection: RootSelection,
    *,
    probe: RootProbe | None = None,
) -> RootResolution:
    """Resolve only the highest-priority configured fact source."""

    selected_origin: RootOrigin | None = None
    candidates: tuple[str | Path, ...] = ()
    for origin, values in (
        (RootOrigin.OVERRIDE, selection.override),
        (RootOrigin.RUNTIME, selection.runtime),
        (RootOrigin.SUPERVISOR, selection.supervisor),
        (RootOrigin.CONFIG, selection.config),
        (RootOrigin.HINT, selection.hints),
    ):
        if values:
            selected_origin = origin
            candidates = values
            break
    if selected_origin is None:
        return RootResolution(roots=(), issues=(), selected_origin=None)

    effective_probe = probe or _probe_root
    roots: list[ResolvedSourceRoot] = []
    issues: list[RootIssue] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            raw_path = Path(candidate).expanduser()
            if not raw_path.is_absolute():
                raise ValueError
            resolved = raw_path.resolve(strict=False)
        except (OSError, RuntimeError, TypeError, ValueError):
            issues.append(RootIssue(selected_origin, SourceCapabilityState.ERROR, "invalid_root"))
            continue
        state = effective_probe(resolved)
        if state is not None:
            issues.append(RootIssue(selected_origin, state, state.value.casefold()))
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(ResolvedSourceRoot(path=resolved, origin=selected_origin))
    return RootResolution(tuple(roots), tuple(issues), selected_origin)


def _probe_root(path: Path) -> SourceCapabilityState | None:
    try:
        if not path.exists():
            return SourceCapabilityState.NOT_FOUND
        if not path.is_dir():
            return SourceCapabilityState.ERROR
        if not os.access(path, os.R_OK | os.X_OK):
            return SourceCapabilityState.NO_PERMISSION
        with os.scandir(path):
            pass
    except PermissionError:
        return SourceCapabilityState.NO_PERMISSION
    except OSError:
        return SourceCapabilityState.ERROR
    return None


def locate_installed_modules(
    roots: tuple[ResolvedSourceRoot, ...],
    installed_modules: Iterable[str],
    *,
    max_modules: int,
    provenance: Mapping[str, SourceProvenance] | None = None,
) -> ModuleInventory:
    names = tuple(dict.fromkeys(installed_modules))
    if len(names) > max_modules:
        return ModuleInventory((), (), (ScanError("module_limit_exceeded"),))
    modules: list[ModuleSource] = []
    missing: list[str] = []
    errors: list[ScanError] = []
    for name in names:
        if not _valid_module_name(name):
            errors.append(ScanError("invalid_module_name"))
            continue
        located: ModuleSource | None = None
        for root in roots:
            candidate = root.path / name
            try:
                if not candidate.exists() or not candidate.is_dir():
                    continue
                resolved = candidate.resolve(strict=True)
                if not _is_within(resolved, root.path):
                    errors.append(ScanError("module_symlink_escape", module=name))
                    break
                manifest = resolved / "__manifest__.py"
                if not manifest.is_file():
                    continue
                located = ModuleSource(
                    name=name,
                    root=root,
                    path=resolved,
                    provenance=(provenance or {}).get(name, SourceProvenance.UNKNOWN),
                )
                break
            except PermissionError:
                errors.append(ScanError("module_no_permission", module=name))
                break
            except OSError:
                errors.append(ScanError("module_error", module=name))
                break
        if located is None:
            missing.append(name)
        else:
            modules.append(located)
    return ModuleInventory(tuple(modules), tuple(missing), tuple(errors))


class _ScanLimitError(RuntimeError):
    pass


class SourceScanner:
    """Orchestrate one deterministic scan over pre-authorized addon roots."""

    def __init__(
        self,
        *,
        store: SourceScanStore,
        extractors: Mapping[SourceFileKind, SourceExtractor],
        limits: ScanLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
        root_probe: RootProbe | None = None,
    ) -> None:
        self._store = store
        self._extractors = dict(extractors)
        self._limits = limits or ScanLimits()
        self._clock = clock
        self._root_probe = root_probe

    def run(
        self,
        *,
        instance_profile_id: UUID,
        roots: RootSelection,
        installed_modules: Iterable[str],
        provenance: Mapping[str, SourceProvenance] | None = None,
    ) -> SourceScanResult:
        resolution = resolve_source_roots(roots, probe=self._root_probe)
        root_errors = tuple(ScanError(issue.code) for issue in resolution.issues)
        if not resolution.roots:
            state = _failed_root_state(resolution.issues)
            self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
            return SourceScanResult(state, None, None, SourceScanMetrics(), root_errors)

        inventory = locate_installed_modules(
            resolution.roots,
            installed_modules,
            max_modules=self._limits.max_modules,
            provenance=provenance,
        )
        initial_errors = (*root_errors, *inventory.issues)
        if not inventory.modules:
            state = (
                SourceCapabilityState.ERROR
                if any(error.code == "module_limit_exceeded" for error in inventory.issues)
                else SourceCapabilityState.NOT_FOUND
            )
            self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
            return SourceScanResult(state, None, None, SourceScanMetrics(), initial_errors)

        scan_id = self._store.open_scan(instance_profile_id=instance_profile_id)
        started = self._clock()
        seen_ids: set[UUID] = set()
        aggregate_items: list[str] = []
        errors = list(initial_errors)
        files_seen = files_extracted = files_unchanged = bytes_hashed = 0
        stale_files = 0
        try:
            for module in inventory.modules:
                for physical_path, logical_path, kind in _iter_module_files(
                    module, self._limits, errors
                ):
                    _check_time(started, self._clock(), self._limits.max_seconds)
                    if files_seen >= self._limits.max_files:
                        raise _ScanLimitError("file_limit_exceeded")
                    files_seen += 1
                    try:
                        metadata = physical_path.stat()
                        if metadata.st_size > self._limits.max_file_bytes:
                            errors.append(ScanError("file_too_large", module.name, logical_path))
                            continue
                        content = physical_path.read_bytes()
                        if len(content) != metadata.st_size:
                            metadata = physical_path.stat()
                        if len(content) > self._limits.max_file_bytes:
                            errors.append(ScanError("file_too_large", module.name, logical_path))
                            continue
                        if bytes_hashed + len(content) > self._limits.max_total_bytes:
                            raise _ScanLimitError("byte_limit_exceeded")
                    except PermissionError:
                        errors.append(ScanError("file_no_permission", module.name, logical_path))
                        continue
                    except OSError:
                        errors.append(ScanError("file_read_error", module.name, logical_path))
                        continue
                    digest = "sha256:" + hashlib.sha256(content).hexdigest()
                    bytes_hashed += len(content)
                    aggregate_items.append(f"{module.name}\0{logical_path}\0{digest}")
                    stored = self._store.upsert_file(
                        scan_run_id=scan_id,
                        module=module.name,
                        logical_path=logical_path,
                        kind=kind,
                        fingerprint=digest,
                        size_bytes=len(content),
                        provenance=module.provenance,
                    )
                    seen_ids.add(stored.file_id)
                    if not stored.fingerprint_changed:
                        files_unchanged += 1
                        continue
                    extractor = self._extractors.get(kind)
                    if extractor is None:
                        errors.append(ScanError("extractor_unavailable", module.name, logical_path))
                        continue
                    try:
                        extraction = extractor.extract(
                            FileScanContext(
                                module=module.name,
                                logical_path=logical_path,
                                kind=kind,
                                fingerprint=digest,
                                size_bytes=len(content),
                                mtime_ns=metadata.st_mtime_ns,
                                content=content,
                            )
                        )
                        self._store.replace_derivatives(
                            source_file_id=stored.file_id,
                            symbols=extraction.symbols,
                            xml_records=extraction.xml_records,
                            metadata=extraction.metadata,
                        )
                        files_extracted += 1
                    except SourceExtractionError as error:
                        errors.append(ScanError(error.code, module.name, logical_path))
                    except Exception:  # noqa: BLE001 - isolate one extractor/file
                        errors.append(ScanError("extractor_error", module.name, logical_path))
            stale_files = self._store.mark_stale(
                scan_run_id=scan_id, seen_file_ids=seen_ids
            )
            aggregate = "\n".join(sorted(aggregate_items)).encode("utf-8")
            fingerprint = "sha256:" + hashlib.sha256(aggregate).hexdigest()
            self._store.finish_scan(
                scan_run_id=scan_id,
                succeeded=True,
                fingerprint=fingerprint,
                error_code=None,
            )
            state = SourceCapabilityState.DETECTED
        except _ScanLimitError as error:
            errors.append(ScanError(str(error)))
            self._store.finish_scan(
                scan_run_id=scan_id,
                succeeded=False,
                fingerprint=None,
                error_code=str(error),
            )
            fingerprint = None
            state = SourceCapabilityState.ERROR
        self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
        return SourceScanResult(
            capability=state,
            scan_run_id=scan_id,
            fingerprint=fingerprint,
            metrics=SourceScanMetrics(
                modules=len(inventory.modules),
                files_seen=files_seen,
                files_extracted=files_extracted,
                files_unchanged=files_unchanged,
                bytes_hashed=bytes_hashed,
                stale_files=stale_files,
            ),
            errors=tuple(errors),
        )


def _iter_module_files(
    module: ModuleSource,
    limits: ScanLimits,
    errors: list[ScanError],
) -> Iterable[tuple[Path, str, SourceFileKind]]:
    stack: list[tuple[Path, PurePosixPath, int]] = [
        (module.path, PurePosixPath(module.name), 0)
    ]
    while stack:
        directory, logical_directory, depth = stack.pop()
        if depth > limits.max_depth:
            raise _ScanLimitError("depth_limit_exceeded")
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except PermissionError:
            errors.append(ScanError("directory_no_permission", module.name))
            continue
        except OSError:
            errors.append(ScanError("directory_read_error", module.name))
            continue
        for entry in reversed(entries):
            path = Path(entry.path)
            logical = logical_directory / entry.name
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                errors.append(ScanError("symlink_error", module.name, str(logical)))
                continue
            if not _is_within(resolved, module.root.path):
                errors.append(ScanError("symlink_escape", module.name, str(logical)))
                continue
            try:
                if resolved.is_dir():
                    if entry.name not in limits.excluded_directories:
                        stack.append((resolved, logical, depth + 1))
                    continue
                if not resolved.is_file():
                    continue
            except OSError:
                errors.append(ScanError("file_stat_error", module.name, str(logical)))
                continue
            kind = _source_kind(entry.name)
            if kind is not None:
                yield resolved, str(logical), kind


def _source_kind(name: str) -> SourceFileKind | None:
    if name == "__manifest__.py":
        return SourceFileKind.MANIFEST
    suffix = Path(name).suffix.casefold()
    return {
        ".py": SourceFileKind.PYTHON,
        ".xml": SourceFileKind.XML,
        ".csv": SourceFileKind.CSV,
    }.get(suffix)


def _failed_root_state(issues: tuple[RootIssue, ...]) -> SourceCapabilityState:
    states = {issue.state for issue in issues}
    if SourceCapabilityState.ERROR in states:
        return SourceCapabilityState.ERROR
    if SourceCapabilityState.NO_PERMISSION in states:
        return SourceCapabilityState.NO_PERMISSION
    return SourceCapabilityState.NOT_FOUND


def _valid_module_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 255
        and _MODULE_NAME.fullmatch(value) is not None
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _check_time(started: float, current: float, limit: float) -> None:
    if current - started > limit:
        raise _ScanLimitError("time_limit_exceeded")
