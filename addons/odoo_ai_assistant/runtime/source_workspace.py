"""Bounded staging workspaces for controlled source-code modification.

This module is intentionally stdlib-only. It can snapshot an installed addon into a
private Assistant workspace, but it never mutates the installed source root and never
places the workspace on Odoo's addons path. Odoo-specific authority resolution is
loaded lazily by the adapter helpers near the bottom of the file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

FORMAT_VERSION = 1
MAX_FILES = 4_096
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_RELATIVE_PATH = 512
MAX_PATH_DEPTH = 24
METADATA_NAME = ".odoo-ai-workspace.json"

_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_WORKSPACE_RE = re.compile(r"^workspace:v1:([0-9a-f]{32})$")
_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "codex_home",
        "filestore",
        "node_modules",
        "secrets",
        "venv",
    }
)
_IGNORED_SOURCE_FILES = frozenset(
    {".env", ".env.local", ".env.production", "id_dsa", "id_ed25519", "id_rsa"}
)
_SECRET_SUFFIXES = frozenset({".key", ".p12", ".pfx", ".pem"})
_METADATA_KEYS = frozenset(
    {
        "format_version",
        "workspace_id",
        "module",
        "source_id",
        "source_fingerprint",
        "baseline_workspace_fingerprint",
        "file_count",
        "total_bytes",
        "binding_fingerprint",
    }
)


class SourceWorkspaceError(RuntimeError):
    """Stable sanitized failure at the source-workspace authority boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceFileEntry:
    logical_path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SourceWorkspaceReceipt:
    workspace_id: str
    module: str
    source_id: str
    source_fingerprint: str
    baseline_workspace_fingerprint: str
    current_workspace_fingerprint: str
    file_count: int
    total_bytes: int
    source_stale: bool | None
    workspace_changed: bool
    binding_fingerprint: str
    current_file_count: int
    current_total_bytes: int
    workspace_path: Path = field(repr=False)

    def public_metadata(self) -> dict[str, object]:
        """Return path-free metadata safe for later capability projection."""

        return {
            "workspace_id": self.workspace_id,
            "module": self.module,
            "source_id": self.source_id,
            "source_fingerprint": self.source_fingerprint,
            "baseline_workspace_fingerprint": self.baseline_workspace_fingerprint,
            "current_workspace_fingerprint": self.current_workspace_fingerprint,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "source_stale": self.source_stale,
            "workspace_changed": self.workspace_changed,
            "binding_fingerprint": self.binding_fingerprint,
            "current_file_count": self.current_file_count,
            "current_total_bytes": self.current_total_bytes,
        }


class SourceWorkspaceStore:
    """Private filesystem store beneath one host-owned mutable runtime root."""

    def __init__(
        self,
        workspace_root: str | os.PathLike[str],
        *,
        max_files: int = MAX_FILES,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        max_file_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        root = Path(workspace_root).expanduser()
        if not root.is_absolute():
            raise SourceWorkspaceError("source_workspace_root_not_absolute")
        if (
            type(max_files) is not int
            or type(max_total_bytes) is not int
            or type(max_file_bytes) is not int
            or not 1 <= max_files <= MAX_FILES
            or not 1 <= max_file_bytes <= MAX_FILE_BYTES
            or not max_file_bytes <= max_total_bytes <= MAX_TOTAL_BYTES
        ):
            raise SourceWorkspaceError("source_workspace_limits_invalid")
        self._workspace_root = root
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes
        self._max_file_bytes = max_file_bytes

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def ensure(self) -> SourceWorkspaceStore:
        self._workspace_root = _ensure_private_directory(self._workspace_root)
        return self

    def prepare(
        self,
        *,
        module: str,
        source_root: str | os.PathLike[str],
        binding: dict[str, object],
    ) -> SourceWorkspaceReceipt:
        """Copy one bounded source snapshot without writing to ``source_root``."""

        module = _module_name(module)
        binding_fingerprint = _binding_fingerprint(binding)
        workspace_root = _ensure_private_directory(self._workspace_root)
        source_root = _source_root(source_root)
        _reject_overlap(source_root, workspace_root)

        entries, payloads = _collect_files(
            source_root,
            max_files=self._max_files,
            max_total_bytes=self._max_total_bytes,
            max_file_bytes=self._max_file_bytes,
            source_mode=True,
        )
        source_id = f"odoo-addon:{module}"
        fingerprint = _snapshot_fingerprint(source_id, entries)
        workspace_id = f"workspace:v1:{uuid4().hex}"
        workspace_hex = _workspace_hex(workspace_id)
        final = workspace_root / workspace_hex
        pending = workspace_root / f".pending-{workspace_hex}"
        if final.exists() or pending.exists():
            raise SourceWorkspaceError("source_workspace_collision")

        try:
            _ensure_private_directory(pending)
            for entry, data in zip(entries, payloads, strict=True):
                target = pending / entry.logical_path
                _ensure_private_directory(target.parent)
                _write_private_file(target, data)
            metadata = {
                "format_version": FORMAT_VERSION,
                "workspace_id": workspace_id,
                "module": module,
                "source_id": source_id,
                "source_fingerprint": fingerprint,
                "baseline_workspace_fingerprint": fingerprint,
                "file_count": len(entries),
                "total_bytes": sum(item.size for item in entries),
                "binding_fingerprint": binding_fingerprint,
            }
            encoded = (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            _write_private_file(pending / METADATA_NAME, encoded)
            _fsync_directory(pending)
            os.replace(pending, final)
            _fsync_directory(workspace_root)
        except Exception:
            if pending.exists():
                _safe_remove_tree(pending, workspace_root)
            raise
        return self.inspect(workspace_id, source_root=source_root, binding=binding)

    def inspect(
        self,
        workspace_id: str,
        *,
        source_root: str | os.PathLike[str] | None = None,
        binding: dict[str, object],
    ) -> SourceWorkspaceReceipt:
        workspace_root = _ensure_private_directory(self._workspace_root)
        workspace_hex = _workspace_hex(workspace_id)
        workspace = _safe_workspace_path(workspace_root, workspace_hex)
        metadata = _read_metadata(workspace)
        if metadata["workspace_id"] != workspace_id:
            raise SourceWorkspaceError("source_workspace_metadata_invalid")

        expected_binding = _binding_fingerprint(binding)
        stored_binding = _fingerprint_value(metadata["binding_fingerprint"])
        if stored_binding != expected_binding:
            raise SourceWorkspaceError("source_workspace_binding_mismatch")

        module = _module_name(metadata["module"])
        source_id = f"odoo-addon:{module}"
        if metadata["source_id"] != source_id:
            raise SourceWorkspaceError("source_workspace_metadata_invalid")
        source_fingerprint = _fingerprint_value(metadata["source_fingerprint"])
        baseline = _fingerprint_value(metadata["baseline_workspace_fingerprint"])
        if baseline != source_fingerprint:
            raise SourceWorkspaceError("source_workspace_metadata_invalid")

        entries, _ = _collect_files(
            workspace,
            max_files=self._max_files,
            max_total_bytes=self._max_total_bytes,
            max_file_bytes=self._max_file_bytes,
            source_mode=False,
        )
        current_workspace = _snapshot_fingerprint(source_id, entries)

        source_stale: bool | None = None
        if source_root is not None:
            resolved_source = _source_root(source_root)
            _reject_overlap(resolved_source, workspace_root)
            source_entries, _ = _collect_files(
                resolved_source,
                max_files=self._max_files,
                max_total_bytes=self._max_total_bytes,
                max_file_bytes=self._max_file_bytes,
                source_mode=True,
            )
            source_stale = (
                _snapshot_fingerprint(source_id, source_entries) != source_fingerprint
            )

        file_count = _bounded_nonnegative_int(metadata["file_count"])
        total_bytes = _bounded_nonnegative_int(metadata["total_bytes"])
        if file_count > self._max_files or total_bytes > self._max_total_bytes:
            raise SourceWorkspaceError("source_workspace_metadata_invalid")

        return SourceWorkspaceReceipt(
            workspace_id=workspace_id,
            module=module,
            source_id=source_id,
            source_fingerprint=source_fingerprint,
            baseline_workspace_fingerprint=baseline,
            current_workspace_fingerprint=current_workspace,
            file_count=file_count,
            total_bytes=total_bytes,
            source_stale=source_stale,
            workspace_changed=current_workspace != baseline,
            binding_fingerprint=stored_binding,
            current_file_count=len(entries),
            current_total_bytes=sum(item.size for item in entries),
            workspace_path=workspace,
        )

    def delete(self, workspace_id: str, *, binding: dict[str, object]) -> None:
        workspace_root = _ensure_private_directory(self._workspace_root)
        workspace_hex = _workspace_hex(workspace_id)
        workspace = _safe_workspace_path(workspace_root, workspace_hex)
        self.inspect(workspace_id, binding=binding)
        _safe_remove_tree(workspace, workspace_root)
        _fsync_directory(workspace_root)


def prepare_installed_module_workspace(context, module: str) -> SourceWorkspaceReceipt:
    """Technical-only Odoo adapter for one installed-addon source snapshot."""

    _require_technical_context(context)
    try:
        from odoo.addons.odoo_ai_assistant.runtime.capabilities.source_evidence import (
            _odoo_module_roots,
        )
        from odoo.addons.odoo_ai_assistant.runtime.paths import RuntimePaths
    except Exception as error:  # pragma: no cover - requires an Odoo registry
        raise SourceWorkspaceError("source_workspace_odoo_adapter_unavailable") from error

    module = _module_name(module)
    root = _odoo_module_roots(context).get(module)
    if root is None:
        raise SourceWorkspaceError("source_workspace_module_unavailable")
    runtime_paths = RuntimePaths.from_odoo()
    store = SourceWorkspaceStore(runtime_paths.source / "workspaces").ensure()
    return store.prepare(module=module, source_root=root, binding=_odoo_binding(context))


def inspect_installed_module_workspace(
    context,
    workspace_id: str,
) -> SourceWorkspaceReceipt:
    """Inspect the workspace plus freshness of its installed source root."""

    _require_technical_context(context)
    try:
        from odoo.addons.odoo_ai_assistant.runtime.capabilities.source_evidence import (
            _odoo_module_roots,
        )
        from odoo.addons.odoo_ai_assistant.runtime.paths import RuntimePaths
    except Exception as error:  # pragma: no cover - requires an Odoo registry
        raise SourceWorkspaceError("source_workspace_odoo_adapter_unavailable") from error

    runtime_paths = RuntimePaths.from_odoo()
    store = SourceWorkspaceStore(runtime_paths.source / "workspaces").ensure()
    binding = _odoo_binding(context)
    initial = store.inspect(workspace_id, binding=binding)
    root = _odoo_module_roots(context).get(initial.module)
    if root is None:
        raise SourceWorkspaceError("source_workspace_module_unavailable")
    return store.inspect(workspace_id, source_root=root, binding=binding)


def delete_installed_module_workspace(context, workspace_id: str) -> None:
    """Delete only a workspace bound to this Technical turn/user."""

    _require_technical_context(context)
    try:
        from odoo.addons.odoo_ai_assistant.runtime.paths import RuntimePaths
    except Exception as error:  # pragma: no cover - requires an Odoo registry
        raise SourceWorkspaceError("source_workspace_odoo_adapter_unavailable") from error
    runtime_paths = RuntimePaths.from_odoo()
    store = SourceWorkspaceStore(runtime_paths.source / "workspaces").ensure()
    store.delete(workspace_id, binding=_odoo_binding(context))


def _odoo_binding(context) -> dict[str, object]:
    env = getattr(context, "env", None)
    uid = getattr(env, "uid", None)
    company_id = getattr(getattr(env, "company", None), "id", None)
    turn_id = getattr(context, "turn_id", None)
    dbname = getattr(getattr(env, "cr", None), "dbname", None)
    if (
        type(uid) is not int
        or uid <= 0
        or type(company_id) is not int
        or company_id <= 0
        or not isinstance(turn_id, str)
        or not 8 <= len(turn_id) <= 128
        or not isinstance(dbname, str)
        or not dbname
    ):
        raise SourceWorkspaceError("source_workspace_binding_invalid")
    return {
        "odoo_uid": uid,
        "company_id": company_id,
        "database_fingerprint": (
            "sha256:" + hashlib.sha256(dbname.encode("utf-8")).hexdigest()
        ),
        "turn_id": turn_id,
    }


def _binding_fingerprint(value: object) -> str:
    if not isinstance(value, dict) or set(value) != {
        "odoo_uid",
        "company_id",
        "database_fingerprint",
        "turn_id",
    }:
        raise SourceWorkspaceError("source_workspace_binding_invalid")
    uid = value.get("odoo_uid")
    company_id = value.get("company_id")
    database = value.get("database_fingerprint")
    turn_id = value.get("turn_id")
    if (
        type(uid) is not int
        or uid <= 0
        or type(company_id) is not int
        or company_id <= 0
        or not isinstance(database, str)
        or len(database) != 71
        or not database.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in database[7:])
        or not isinstance(turn_id, str)
        or not 8 <= len(turn_id) <= 128
        or "\x00" in turn_id
    ):
        raise SourceWorkspaceError("source_workspace_binding_invalid")
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _require_technical_context(context) -> None:
    user = getattr(getattr(context, "env", None), "user", None)
    try:
        allowed = bool(user and user.has_group("base.group_system"))
    except Exception as error:
        raise SourceWorkspaceError("source_workspace_technical_required") from error
    if not allowed:
        raise SourceWorkspaceError("source_workspace_technical_required")


def _module_name(value: object) -> str:
    if not isinstance(value, str) or _MODULE_RE.fullmatch(value) is None:
        raise SourceWorkspaceError("source_workspace_module_invalid")
    return value


def _workspace_hex(value: object) -> str:
    if not isinstance(value, str):
        raise SourceWorkspaceError("source_workspace_id_invalid")
    match = _WORKSPACE_RE.fullmatch(value)
    if match is None:
        raise SourceWorkspaceError("source_workspace_id_invalid")
    return match.group(1)


def _source_root(value: str | os.PathLike[str]) -> Path:
    raw = Path(value).expanduser()
    try:
        if raw.is_symlink():
            raise SourceWorkspaceError("source_workspace_source_symlink")
        resolved = raw.resolve(strict=True)
        if not resolved.is_dir() or resolved.is_symlink():
            raise SourceWorkspaceError("source_workspace_source_invalid")
        return resolved
    except SourceWorkspaceError:
        raise
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_source_unavailable") from error


def _ensure_private_directory(path: Path) -> Path:
    try:
        if path.exists() and path.is_symlink():
            raise SourceWorkspaceError("source_workspace_path_symlink")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_dir() or resolved.is_symlink():
            raise SourceWorkspaceError("source_workspace_path_invalid")
        resolved.chmod(0o700)
        return resolved
    except SourceWorkspaceError:
        raise
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_path_unavailable") from error


def _reject_overlap(source_root: Path, workspace_root: Path) -> None:
    if _is_relative_to(source_root, workspace_root) or _is_relative_to(
        workspace_root,
        source_root,
    ):
        raise SourceWorkspaceError("source_workspace_root_overlap")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_workspace_path(workspace_root: Path, workspace_hex: str) -> Path:
    candidate = workspace_root / workspace_hex
    try:
        if candidate.is_symlink():
            raise SourceWorkspaceError("source_workspace_path_symlink")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir() or not _is_relative_to(resolved, workspace_root):
            raise SourceWorkspaceError("source_workspace_path_invalid")
        return resolved
    except SourceWorkspaceError:
        raise
    except FileNotFoundError:
        raise SourceWorkspaceError("source_workspace_not_found") from None
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_path_unavailable") from error


def _collect_files(
    root: Path,
    *,
    max_files: int,
    max_total_bytes: int,
    max_file_bytes: int,
    source_mode: bool,
) -> tuple[tuple[SourceFileEntry, ...], tuple[bytes, ...]]:
    entries: list[SourceFileEntry] = []
    payloads: list[bytes] = []
    total_bytes = 0

    for directory, dirnames, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        directory_path = Path(directory)
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            child = directory_path / name
            if name in _IGNORED_DIRS:
                continue
            if child.is_symlink():
                raise SourceWorkspaceError("source_workspace_source_symlink")
            if _is_secret_name(name):
                if source_mode:
                    continue
                raise SourceWorkspaceError("source_workspace_secret_entry")
            kept_dirs.append(name)
        dirnames[:] = kept_dirs

        for name in sorted(filenames):
            if name == METADATA_NAME:
                if source_mode:
                    raise SourceWorkspaceError("source_workspace_reserved_name")
                continue
            if _is_secret_name(name):
                if source_mode:
                    continue
                raise SourceWorkspaceError("source_workspace_secret_entry")
            path = directory_path / name
            if path.is_symlink():
                raise SourceWorkspaceError("source_workspace_source_symlink")
            relative = path.relative_to(root).as_posix()
            _validate_relative_path(relative)
            data = _read_regular_file(path, max_file_bytes=max_file_bytes)
            total_bytes += len(data)
            if total_bytes > max_total_bytes:
                raise SourceWorkspaceError("source_workspace_total_too_large")
            entries.append(
                SourceFileEntry(
                    relative,
                    len(data),
                    hashlib.sha256(data).hexdigest(),
                )
            )
            payloads.append(data)
            if len(entries) > max_files:
                raise SourceWorkspaceError("source_workspace_too_many_files")

    paired = sorted(
        zip(entries, payloads, strict=True),
        key=lambda item: item[0].logical_path,
    )
    if not paired:
        raise SourceWorkspaceError("source_workspace_empty")
    return tuple(item[0] for item in paired), tuple(item[1] for item in paired)


def _validate_relative_path(value: str) -> None:
    parts = Path(value).parts
    if (
        not value
        or value.startswith(("/", "\\"))
        or len(value) > MAX_RELATIVE_PATH
        or len(parts) > MAX_PATH_DEPTH
        or any(part in {"", ".", ".."} for part in parts)
        or any("\x00" in part or "\n" in part or "\r" in part for part in parts)
    ):
        raise SourceWorkspaceError("source_workspace_relative_path_invalid")


def _read_regular_file(path: Path, *, max_file_bytes: int) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_file_unavailable") from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SourceWorkspaceError("source_workspace_file_not_regular")
        if info.st_size > max_file_bytes:
            raise SourceWorkspaceError("source_workspace_file_too_large")
        chunks: list[bytes] = []
        remaining = max_file_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_file_bytes:
            raise SourceWorkspaceError("source_workspace_file_too_large")
        return data
    finally:
        os.close(fd)


def _snapshot_fingerprint(
    source_id: str,
    entries: tuple[SourceFileEntry, ...],
) -> str:
    payload = {
        "format_version": FORMAT_VERSION,
        "source_id": source_id,
        "files": [
            {
                "logical_path": item.logical_path,
                "size": item.size,
                "sha256": item.sha256,
            }
            for item in entries
        ],
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write_private_file(path: Path, data: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_write_failed") from error
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise SourceWorkspaceError("source_workspace_write_failed")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_metadata(workspace: Path) -> dict[str, object]:
    raw = _read_regular_file(workspace / METADATA_NAME, max_file_bytes=16 * 1024)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SourceWorkspaceError("source_workspace_metadata_invalid") from None
    if (
        not isinstance(value, dict)
        or set(value) != _METADATA_KEYS
        or value.get("format_version") != FORMAT_VERSION
    ):
        raise SourceWorkspaceError("source_workspace_metadata_invalid")
    return value


def _fingerprint_value(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise SourceWorkspaceError("source_workspace_metadata_invalid")
    return value


def _bounded_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise SourceWorkspaceError("source_workspace_metadata_invalid")
    return value


def _is_secret_name(name: str) -> bool:
    folded = name.casefold()
    return (
        folded in _IGNORED_SOURCE_FILES
        or Path(folded).suffix in _SECRET_SUFFIXES
        or folded.endswith(".secret")
        or folded.startswith("credentials.")
    )


def _safe_remove_tree(path: Path, workspace_root: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        return
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_cleanup_failed") from error
    if resolved == workspace_root or not _is_relative_to(resolved, workspace_root):
        raise SourceWorkspaceError("source_workspace_cleanup_boundary")
    try:
        shutil.rmtree(resolved)
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_cleanup_failed") from error


def _fsync_directory(path: Path) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise SourceWorkspaceError("source_workspace_fsync_failed") from error
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


__all__ = [
    "FORMAT_VERSION",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_BYTES",
    "SourceFileEntry",
    "SourceWorkspaceError",
    "SourceWorkspaceReceipt",
    "SourceWorkspaceStore",
    "delete_installed_module_workspace",
    "inspect_installed_module_workspace",
    "prepare_installed_module_workspace",
]
