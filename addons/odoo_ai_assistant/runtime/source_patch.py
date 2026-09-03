"""Typed workspace-only source patching for Phase 12.

Patch input is a bounded structured edit contract, never a shell/Git command or a
filesystem root. Applying a patch materializes a new derived private workspace and
keeps the parent workspace unchanged as the rollback boundary.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

try:  # Dependency-light tests import runtime modules directly from this directory.
    from .source_workspace import (
        FORMAT_VERSION,
        MAX_FILES,
        MAX_FILE_BYTES,
        MAX_TOTAL_BYTES,
        METADATA_NAME,
        SourceFileEntry,
        SourceWorkspaceError,
        SourceWorkspaceReceipt,
        SourceWorkspaceStore,
        _collect_files,
        _ensure_private_directory,
        _fingerprint_value,
        _fsync_directory,
        _is_relative_to,
        _is_secret_name,
        _odoo_binding,
        _read_regular_file,
        _require_technical_context,
        _safe_remove_tree,
        _snapshot_fingerprint,
        _validate_relative_path,
        _workspace_hex,
        _write_private_file,
    )
except ImportError:  # pragma: no cover - dependency-light direct import.
    from source_workspace import (
        FORMAT_VERSION,
        MAX_FILES,
        MAX_FILE_BYTES,
        MAX_TOTAL_BYTES,
        METADATA_NAME,
        SourceFileEntry,
        SourceWorkspaceError,
        SourceWorkspaceReceipt,
        SourceWorkspaceStore,
        _collect_files,
        _ensure_private_directory,
        _fingerprint_value,
        _fsync_directory,
        _is_relative_to,
        _is_secret_name,
        _odoo_binding,
        _read_regular_file,
        _require_technical_context,
        _safe_remove_tree,
        _snapshot_fingerprint,
        _validate_relative_path,
        _workspace_hex,
        _write_private_file,
    )

PATCH_FORMAT_VERSION = 1
PATCH_RECEIPT_DIR = ".patch-receipts"
MAX_CHANGED_FILES = 12
MAX_EDITS_PER_FILE = 16
MAX_TOTAL_EDITS = 48
MAX_EDIT_TEXT_BYTES = 64 * 1024
MAX_PATCH_FILE_BYTES = 512 * 1024
MAX_PATCH_TOTAL_TEXT_BYTES = 2 * 1024 * 1024
MAX_DIFF_BYTES = 48 * 1024
MAX_READ_LINES = 240
MAX_READ_BYTES = 32 * 1024

_PATCHABLE_SUFFIXES = frozenset(
    {
        ".css",
        ".csv",
        ".js",
        ".json",
        ".md",
        ".po",
        ".pot",
        ".py",
        ".rst",
        ".scss",
        ".txt",
        ".xml",
    }
)
_FORBIDDEN_PARTS = frozenset(
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
_PATCH_RECEIPT_KEYS = frozenset(
    {
        "format_version",
        "workspace_id",
        "parent_workspace_id",
        "module",
        "source_id",
        "source_fingerprint",
        "before_workspace_fingerprint",
        "after_workspace_fingerprint",
        "diff_fingerprint",
        "approval_fingerprint",
        "binding_fingerprint",
        "changed_paths",
        "change_count",
    }
)


class SourcePatchError(RuntimeError):
    """Stable sanitized failure for the staged source patch boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourcePatchPreview:
    workspace_id: str
    module: str
    source_id: str
    source_fingerprint: str
    before_workspace_fingerprint: str
    after_workspace_fingerprint: str
    diff_fingerprint: str
    approval_fingerprint: str
    changed_files: tuple[dict[str, object], ...]
    change_count: int
    diff: str
    source_stale: bool | None
    _payloads: dict[str, bytes] = field(repr=False)
    _entries: tuple[SourceFileEntry, ...] = field(repr=False)
    _normalized_changes: tuple[dict[str, object], ...] = field(repr=False)

    def public_metadata(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "module": self.module,
            "source_id": self.source_id,
            "source_fingerprint": self.source_fingerprint,
            "before_workspace_fingerprint": self.before_workspace_fingerprint,
            "after_workspace_fingerprint": self.after_workspace_fingerprint,
            "diff_fingerprint": self.diff_fingerprint,
            "approval_fingerprint": self.approval_fingerprint,
            "changed_files": [dict(item) for item in self.changed_files],
            "change_count": self.change_count,
            "diff": self.diff,
            "source_stale": self.source_stale,
        }


@dataclass(frozen=True, slots=True)
class SourcePatchReceipt:
    workspace_id: str
    parent_workspace_id: str
    module: str
    source_id: str
    source_fingerprint: str
    before_workspace_fingerprint: str
    after_workspace_fingerprint: str
    diff_fingerprint: str
    approval_fingerprint: str
    binding_fingerprint: str
    changed_paths: tuple[str, ...]
    change_count: int
    source_stale: bool | None
    workspace_path: Path = field(repr=False)

    def public_metadata(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "parent_workspace_id": self.parent_workspace_id,
            "module": self.module,
            "source_id": self.source_id,
            "source_fingerprint": self.source_fingerprint,
            "before_workspace_fingerprint": self.before_workspace_fingerprint,
            "after_workspace_fingerprint": self.after_workspace_fingerprint,
            "diff_fingerprint": self.diff_fingerprint,
            "approval_fingerprint": self.approval_fingerprint,
            "binding_fingerprint": self.binding_fingerprint,
            "changed_paths": list(self.changed_paths),
            "change_count": self.change_count,
            "source_stale": self.source_stale,
        }


class SourcePatchStore:
    """Preview and materialize typed edits under a SourceWorkspaceStore."""

    def __init__(self, workspace_store: SourceWorkspaceStore) -> None:
        if not isinstance(workspace_store, SourceWorkspaceStore):
            raise SourcePatchError("source_patch_store_invalid")
        self._store = workspace_store.ensure()

    def preview(
        self,
        *,
        workspace_id: str,
        expected_workspace_fingerprint: str,
        changes,
        binding: dict[str, object],
        source_root: str | os.PathLike[str] | None = None,
    ) -> SourcePatchPreview:
        expected = _patch_fingerprint(expected_workspace_fingerprint)
        try:
            receipt = self._store.inspect(
                workspace_id,
                source_root=source_root,
                binding=binding,
            )
        except SourceWorkspaceError as error:
            raise SourcePatchError(error.code) from None
        if receipt.source_stale is True:
            raise SourcePatchError("source_patch_source_stale")
        if receipt.current_workspace_fingerprint != expected:
            raise SourcePatchError("source_patch_workspace_stale")

        normalized = _normalize_changes(changes)
        entries, payloads = _collect_workspace_payloads(self._store, receipt)
        del entries
        before_payloads = dict(payloads)
        after_payloads = dict(payloads)
        changed_files: list[dict[str, object]] = []
        total_edit_text = 0
        total_edits = 0

        for change in normalized:
            path = str(change["path"])
            action = str(change["action"])
            before = before_payloads.get(path)
            if action == "create":
                if before is not None:
                    raise SourcePatchError("source_patch_create_exists")
                after = _text_bytes(change["content"], allow_empty=False)
                total_edit_text += len(after)
                after_payloads[path] = after
                edit_count = 1
            elif action == "delete":
                if before is None:
                    raise SourcePatchError("source_patch_delete_missing")
                _decode_patch_text(before)
                after = None
                del after_payloads[path]
                edit_count = 1
            else:
                if before is None:
                    raise SourcePatchError("source_patch_modify_missing")
                text = _decode_patch_text(before)
                edits = change["edits"]
                if not isinstance(edits, tuple):
                    raise SourcePatchError("source_patch_invalid")
                edit_count = len(edits)
                for edit in edits:
                    old = str(edit["old"])
                    new = str(edit["new"])
                    old_bytes = _text_bytes(old, allow_empty=False)
                    new_bytes = _text_bytes(new, allow_empty=True)
                    total_edit_text += len(old_bytes) + len(new_bytes)
                    if old == new:
                        raise SourcePatchError("source_patch_no_effect")
                    if text.count(old) != 1:
                        raise SourcePatchError("source_patch_match_not_unique")
                    text = text.replace(old, new, 1)
                after = _text_bytes(text, allow_empty=True)
                if after == before:
                    raise SourcePatchError("source_patch_no_effect")
                after_payloads[path] = after

            total_edits += edit_count
            if total_edits > MAX_TOTAL_EDITS or total_edit_text > MAX_PATCH_TOTAL_TEXT_BYTES:
                raise SourcePatchError("source_patch_too_large")
            if after is not None and len(after) > MAX_PATCH_FILE_BYTES:
                raise SourcePatchError("source_patch_file_too_large")
            if before is not None and len(before) > MAX_PATCH_FILE_BYTES:
                raise SourcePatchError("source_patch_file_too_large")

            before_sha = hashlib.sha256(before).hexdigest() if before is not None else None
            after_sha = hashlib.sha256(after).hexdigest() if after is not None else None
            diff_text = _file_diff(path, before, after)
            additions, deletions = _diff_counts(diff_text)
            changed_files.append(
                {
                    "path": path,
                    "action": action,
                    "before_sha256": before_sha,
                    "after_sha256": after_sha,
                    "additions": additions,
                    "deletions": deletions,
                }
            )

        after_entries = _entries_for_payloads(after_payloads)
        _enforce_store_bounds(self._store, after_entries)
        after_fingerprint = _snapshot_fingerprint(receipt.source_id, after_entries)
        if after_fingerprint == receipt.current_workspace_fingerprint:
            raise SourcePatchError("source_patch_no_effect")

        full_diff = "".join(
            _file_diff(
                str(change["path"]),
                before_payloads.get(str(change["path"])),
                after_payloads.get(str(change["path"])),
            )
            for change in normalized
        )
        encoded_diff = full_diff.encode("utf-8")
        if not encoded_diff or len(encoded_diff) > MAX_DIFF_BYTES:
            raise SourcePatchError("source_patch_diff_too_large")
        diff_fingerprint = "sha256:" + hashlib.sha256(encoded_diff).hexdigest()
        approval_fingerprint = _json_fingerprint(
            {
                "format_version": PATCH_FORMAT_VERSION,
                "workspace_id": receipt.workspace_id,
                "source_fingerprint": receipt.source_fingerprint,
                "before_workspace_fingerprint": receipt.current_workspace_fingerprint,
                "after_workspace_fingerprint": after_fingerprint,
                "diff_fingerprint": diff_fingerprint,
                "changes": normalized,
            }
        )
        return SourcePatchPreview(
            workspace_id=receipt.workspace_id,
            module=receipt.module,
            source_id=receipt.source_id,
            source_fingerprint=receipt.source_fingerprint,
            before_workspace_fingerprint=receipt.current_workspace_fingerprint,
            after_workspace_fingerprint=after_fingerprint,
            diff_fingerprint=diff_fingerprint,
            approval_fingerprint=approval_fingerprint,
            changed_files=tuple(changed_files),
            change_count=len(normalized),
            diff=full_diff,
            source_stale=receipt.source_stale,
            _payloads=after_payloads,
            _entries=after_entries,
            _normalized_changes=normalized,
        )

    def apply(
        self,
        *,
        workspace_id: str,
        expected_workspace_fingerprint: str,
        changes,
        binding: dict[str, object],
        source_root: str | os.PathLike[str] | None = None,
    ) -> SourcePatchReceipt:
        preview = self.preview(
            workspace_id=workspace_id,
            expected_workspace_fingerprint=expected_workspace_fingerprint,
            changes=changes,
            binding=binding,
            source_root=source_root,
        )
        try:
            parent = self._store.inspect(
                workspace_id,
                source_root=source_root,
                binding=binding,
            )
        except SourceWorkspaceError as error:
            raise SourcePatchError(error.code) from None
        if parent.current_workspace_fingerprint != preview.before_workspace_fingerprint:
            raise SourcePatchError("source_patch_workspace_stale")

        workspace_root = self._store.workspace_root
        derived_id = f"workspace:v1:{uuid4().hex}"
        derived_hex = _workspace_hex(derived_id)
        final = workspace_root / derived_hex
        pending = workspace_root / f".pending-{derived_hex}"
        if final.exists() or pending.exists():
            raise SourcePatchError("source_patch_workspace_collision")

        receipt_root = _ensure_private_directory(workspace_root / PATCH_RECEIPT_DIR)
        receipt_path = receipt_root / f"{derived_hex}.json"
        if receipt_path.exists():
            raise SourcePatchError("source_patch_receipt_collision")

        try:
            _ensure_private_directory(pending)
            for entry in preview._entries:
                data = preview._payloads[entry.logical_path]
                target = pending / entry.logical_path
                _ensure_private_directory(target.parent)
                _write_private_file(target, data)

            workspace_metadata = {
                "format_version": FORMAT_VERSION,
                "workspace_id": derived_id,
                "module": parent.module,
                "source_id": parent.source_id,
                "source_fingerprint": parent.source_fingerprint,
                "baseline_workspace_fingerprint": parent.baseline_workspace_fingerprint,
                "file_count": parent.file_count,
                "total_bytes": parent.total_bytes,
                "binding_fingerprint": parent.binding_fingerprint,
            }
            _write_private_file(pending / METADATA_NAME, _json_bytes(workspace_metadata))
            _fsync_directory(pending)
            os.replace(pending, final)
            _fsync_directory(workspace_root)

            patch_metadata = {
                "format_version": PATCH_FORMAT_VERSION,
                "workspace_id": derived_id,
                "parent_workspace_id": parent.workspace_id,
                "module": parent.module,
                "source_id": parent.source_id,
                "source_fingerprint": parent.source_fingerprint,
                "before_workspace_fingerprint": preview.before_workspace_fingerprint,
                "after_workspace_fingerprint": preview.after_workspace_fingerprint,
                "diff_fingerprint": preview.diff_fingerprint,
                "approval_fingerprint": preview.approval_fingerprint,
                "binding_fingerprint": parent.binding_fingerprint,
                "changed_paths": [str(item["path"]) for item in preview.changed_files],
                "change_count": preview.change_count,
            }
            _write_private_file(receipt_path, _json_bytes(patch_metadata))
            _fsync_directory(receipt_root)
        except (OSError, SourceWorkspaceError) as error:
            if final.exists():
                _safe_remove_tree(final, workspace_root)
            if pending.exists():
                _safe_remove_tree(pending, workspace_root)
            try:
                receipt_path.unlink(missing_ok=True)
            except OSError:
                pass
            code = error.code if isinstance(error, SourceWorkspaceError) else "source_patch_write_failed"
            raise SourcePatchError(code) from None

        return self.inspect_receipt(
            derived_id,
            binding=binding,
            source_root=source_root,
        )

    def inspect_receipt(
        self,
        workspace_id: str,
        *,
        binding: dict[str, object],
        source_root: str | os.PathLike[str] | None = None,
    ) -> SourcePatchReceipt:
        try:
            workspace = self._store.inspect(
                workspace_id,
                source_root=source_root,
                binding=binding,
            )
            derived_hex = _workspace_hex(workspace_id)
        except SourceWorkspaceError as error:
            raise SourcePatchError(error.code) from None
        receipt_path = self._store.workspace_root / PATCH_RECEIPT_DIR / f"{derived_hex}.json"
        try:
            raw = _read_regular_file(receipt_path, max_file_bytes=32 * 1024)
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, SourceWorkspaceError):
            raise SourcePatchError("source_patch_receipt_invalid") from None
        if (
            not isinstance(value, dict)
            or set(value) != _PATCH_RECEIPT_KEYS
            or value.get("format_version") != PATCH_FORMAT_VERSION
            or value.get("workspace_id") != workspace_id
            or value.get("module") != workspace.module
            or value.get("source_id") != workspace.source_id
            or value.get("source_fingerprint") != workspace.source_fingerprint
            or value.get("after_workspace_fingerprint") != workspace.current_workspace_fingerprint
            or value.get("binding_fingerprint") != workspace.binding_fingerprint
        ):
            raise SourcePatchError("source_patch_receipt_invalid")
        parent_id = value.get("parent_workspace_id")
        if not isinstance(parent_id, str):
            raise SourcePatchError("source_patch_receipt_invalid")
        try:
            parent = self._store.inspect(parent_id, binding=binding)
        except SourceWorkspaceError:
            raise SourcePatchError("source_patch_parent_invalid") from None
        if parent.current_workspace_fingerprint != value.get("before_workspace_fingerprint"):
            raise SourcePatchError("source_patch_parent_stale")

        changed_paths = value.get("changed_paths")
        change_count = value.get("change_count")
        if (
            not isinstance(changed_paths, list)
            or not 1 <= len(changed_paths) <= MAX_CHANGED_FILES
            or any(not isinstance(item, str) for item in changed_paths)
            or len(set(changed_paths)) != len(changed_paths)
            or type(change_count) is not int
            or change_count != len(changed_paths)
        ):
            raise SourcePatchError("source_patch_receipt_invalid")
        for path in changed_paths:
            _patchable_path(path)
        diff_fingerprint = _patch_fingerprint(value.get("diff_fingerprint"))
        approval_fingerprint = _patch_fingerprint(value.get("approval_fingerprint"))
        before_fingerprint = _patch_fingerprint(value.get("before_workspace_fingerprint"))
        after_fingerprint = _patch_fingerprint(value.get("after_workspace_fingerprint"))
        return SourcePatchReceipt(
            workspace_id=workspace_id,
            parent_workspace_id=parent_id,
            module=workspace.module,
            source_id=workspace.source_id,
            source_fingerprint=workspace.source_fingerprint,
            before_workspace_fingerprint=before_fingerprint,
            after_workspace_fingerprint=after_fingerprint,
            diff_fingerprint=diff_fingerprint,
            approval_fingerprint=approval_fingerprint,
            binding_fingerprint=workspace.binding_fingerprint,
            changed_paths=tuple(changed_paths),
            change_count=change_count,
            source_stale=workspace.source_stale,
            workspace_path=workspace.workspace_path,
        )


def inspect_installed_module_source(context, module: str) -> dict[str, object]:
    """Return path-free current installed-source metadata without creating a workspace."""

    _require_technical_context(context)
    try:
        from odoo.addons.odoo_ai_assistant.runtime.capabilities.source_evidence import (
            _odoo_module_roots,
        )
    except Exception as error:  # pragma: no cover - Odoo registry boundary.
        raise SourcePatchError("source_patch_odoo_adapter_unavailable") from error
    roots = _odoo_module_roots(context)
    root = roots.get(module)
    if root is None:
        raise SourcePatchError("source_workspace_module_unavailable")
    try:
        entries, _ = _collect_files(
            Path(root).resolve(strict=True),
            max_files=MAX_FILES,
            max_total_bytes=MAX_TOTAL_BYTES,
            max_file_bytes=MAX_FILE_BYTES,
            source_mode=True,
        )
    except (OSError, SourceWorkspaceError) as error:
        code = error.code if isinstance(error, SourceWorkspaceError) else "source_workspace_source_unavailable"
        raise SourcePatchError(code) from None
    source_id = f"odoo-addon:{module}"
    return {
        "module": module,
        "source_id": source_id,
        "source_fingerprint": _snapshot_fingerprint(source_id, entries),
        "file_count": len(entries),
        "total_bytes": sum(item.size for item in entries),
    }


def preview_installed_workspace_patch(
    context,
    *,
    workspace_id: str,
    expected_workspace_fingerprint: str,
    changes,
) -> SourcePatchPreview:
    _require_technical_context(context)
    store, binding, root = _odoo_patch_store(context, workspace_id)
    return SourcePatchStore(store).preview(
        workspace_id=workspace_id,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
        changes=changes,
        binding=binding,
        source_root=root,
    )


def apply_installed_workspace_patch(
    context,
    *,
    workspace_id: str,
    expected_workspace_fingerprint: str,
    changes,
) -> SourcePatchReceipt:
    _require_technical_context(context)
    store, binding, root = _odoo_patch_store(context, workspace_id)
    return SourcePatchStore(store).apply(
        workspace_id=workspace_id,
        expected_workspace_fingerprint=expected_workspace_fingerprint,
        changes=changes,
        binding=binding,
        source_root=root,
    )


def inspect_installed_patch_receipt(context, workspace_id: str) -> SourcePatchReceipt:
    _require_technical_context(context)
    store, binding, root = _odoo_patch_store(context, workspace_id)
    return SourcePatchStore(store).inspect_receipt(
        workspace_id,
        binding=binding,
        source_root=root,
    )


def read_installed_workspace_file(
    context,
    *,
    workspace_id: str,
    logical_path: str,
    start_line: int = 1,
    max_lines: int = 120,
) -> dict[str, object]:
    _require_technical_context(context)
    if type(start_line) is not int or start_line < 1:
        raise SourcePatchError("source_patch_read_range_invalid")
    if type(max_lines) is not int or not 1 <= max_lines <= MAX_READ_LINES:
        raise SourcePatchError("source_patch_read_range_invalid")
    store, binding, root = _odoo_patch_store(context, workspace_id)
    try:
        receipt = store.inspect(workspace_id, source_root=root, binding=binding)
    except SourceWorkspaceError as error:
        raise SourcePatchError(error.code) from None
    path = _patchable_path(logical_path)
    candidate = receipt.workspace_path / path
    try:
        resolved = candidate.resolve(strict=True)
        if (
            candidate.is_symlink()
            or not resolved.is_file()
            or not _is_relative_to(resolved, receipt.workspace_path)
        ):
            raise SourcePatchError("source_patch_file_invalid")
        raw = _read_regular_file(resolved, max_file_bytes=MAX_PATCH_FILE_BYTES)
    except SourcePatchError:
        raise
    except (OSError, SourceWorkspaceError) as error:
        code = error.code if isinstance(error, SourceWorkspaceError) else "source_patch_file_invalid"
        raise SourcePatchError(code) from None
    text = _decode_patch_text(raw)
    lines = text.splitlines()
    start = min(start_line - 1, len(lines))
    selected = lines[start : start + max_lines]
    excerpt = "\n".join(selected)
    if len(excerpt.encode("utf-8")) > MAX_READ_BYTES:
        while selected and len("\n".join(selected).encode("utf-8")) > MAX_READ_BYTES:
            selected.pop()
        excerpt = "\n".join(selected)
    return {
        "workspace_id": workspace_id,
        "module": receipt.module,
        "logical_path": path,
        "workspace_fingerprint": receipt.current_workspace_fingerprint,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "line_start": start + 1 if selected else start_line,
        "line_end": start + len(selected),
        "text": excerpt,
        "truncated": start + len(selected) < len(lines),
        "source_stale": receipt.source_stale,
    }


def _odoo_patch_store(context, workspace_id: str):
    try:
        from odoo.addons.odoo_ai_assistant.runtime.capabilities.source_evidence import (
            _odoo_module_roots,
        )
        from odoo.addons.odoo_ai_assistant.runtime.paths import RuntimePaths
    except Exception as error:  # pragma: no cover - Odoo registry boundary.
        raise SourcePatchError("source_patch_odoo_adapter_unavailable") from error
    paths = RuntimePaths.from_odoo()
    store = SourceWorkspaceStore(paths.source / "workspaces").ensure()
    binding = _odoo_binding(context)
    try:
        initial = store.inspect(workspace_id, binding=binding)
    except SourceWorkspaceError as error:
        raise SourcePatchError(error.code) from None
    root = _odoo_module_roots(context).get(initial.module)
    if root is None:
        raise SourcePatchError("source_workspace_module_unavailable")
    return store, binding, root


def _normalize_changes(value) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_CHANGED_FILES:
        raise SourcePatchError("source_patch_invalid")
    result: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    total_edits = 0
    for item in value:
        if not isinstance(item, dict):
            raise SourcePatchError("source_patch_invalid")
        path = _patchable_path(item.get("path"))
        action = item.get("action")
        if action == "modify":
            if set(item) != {"path", "action", "edits"}:
                raise SourcePatchError("source_patch_invalid")
            edits = item.get("edits")
            if not isinstance(edits, (list, tuple)) or not 1 <= len(edits) <= MAX_EDITS_PER_FILE:
                raise SourcePatchError("source_patch_invalid")
            normalized_edits = []
            for edit in edits:
                if not isinstance(edit, dict) or set(edit) != {"old", "new"}:
                    raise SourcePatchError("source_patch_invalid")
                old = edit.get("old")
                new = edit.get("new")
                _text_bytes(old, allow_empty=False)
                _text_bytes(new, allow_empty=True)
                normalized_edits.append({"old": old, "new": new})
            total_edits += len(normalized_edits)
            normalized = {"path": path, "action": "modify", "edits": tuple(normalized_edits)}
        elif action == "create":
            if set(item) != {"path", "action", "content"}:
                raise SourcePatchError("source_patch_invalid")
            content = item.get("content")
            _text_bytes(content, allow_empty=False)
            total_edits += 1
            normalized = {"path": path, "action": "create", "content": content}
        elif action == "delete":
            if set(item) != {"path", "action"}:
                raise SourcePatchError("source_patch_invalid")
            total_edits += 1
            normalized = {"path": path, "action": "delete"}
        else:
            raise SourcePatchError("source_patch_invalid")
        if path in seen_paths:
            raise SourcePatchError("source_patch_duplicate_path")
        seen_paths.add(path)
        result.append(normalized)
    if total_edits > MAX_TOTAL_EDITS:
        raise SourcePatchError("source_patch_too_large")
    return tuple(sorted(result, key=lambda item: str(item["path"])))


def _patchable_path(value) -> str:
    if not isinstance(value, str):
        raise SourcePatchError("source_patch_path_invalid")
    try:
        _validate_relative_path(value)
    except SourceWorkspaceError:
        raise SourcePatchError("source_patch_path_invalid") from None
    parts = Path(value).parts
    if (
        value == METADATA_NAME
        or any(part in _FORBIDDEN_PARTS or _is_secret_name(part) for part in parts)
        or Path(value).suffix.casefold() not in _PATCHABLE_SUFFIXES
    ):
        raise SourcePatchError("source_patch_path_not_allowed")
    return Path(value).as_posix()


def _text_bytes(value, *, allow_empty: bool) -> bytes:
    if not isinstance(value, str) or "\x00" in value or (not allow_empty and not value):
        raise SourcePatchError("source_patch_text_invalid")
    data = value.encode("utf-8")
    if not allow_empty and len(data) > MAX_EDIT_TEXT_BYTES:
        raise SourcePatchError("source_patch_edit_too_large")
    if len(data) > MAX_PATCH_FILE_BYTES:
        raise SourcePatchError("source_patch_file_too_large")
    return data


def _decode_patch_text(value: bytes) -> str:
    if len(value) > MAX_PATCH_FILE_BYTES:
        raise SourcePatchError("source_patch_file_too_large")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        raise SourcePatchError("source_patch_file_not_text") from None
    if "\x00" in text:
        raise SourcePatchError("source_patch_file_not_text")
    return text


def _collect_workspace_payloads(store: SourceWorkspaceStore, receipt: SourceWorkspaceReceipt):
    try:
        entries, payloads = _collect_files(
            receipt.workspace_path,
            max_files=store._max_files,
            max_total_bytes=store._max_total_bytes,
            max_file_bytes=store._max_file_bytes,
            source_mode=False,
        )
    except SourceWorkspaceError as error:
        raise SourcePatchError(error.code) from None
    if _snapshot_fingerprint(receipt.source_id, entries) != receipt.current_workspace_fingerprint:
        raise SourcePatchError("source_patch_workspace_stale")
    return entries, {
        entry.logical_path: data
        for entry, data in zip(entries, payloads, strict=True)
    }


def _entries_for_payloads(payloads: dict[str, bytes]) -> tuple[SourceFileEntry, ...]:
    entries = []
    for path, data in sorted(payloads.items()):
        _existing_path_safe(path)
        entries.append(SourceFileEntry(path, len(data), hashlib.sha256(data).hexdigest()))
    return tuple(entries)


def _existing_path_safe(path: str) -> None:
    try:
        _validate_relative_path(path)
    except SourceWorkspaceError:
        raise SourcePatchError("source_patch_path_invalid") from None
    parts = Path(path).parts
    if any(part in _FORBIDDEN_PARTS or _is_secret_name(part) for part in parts):
        raise SourcePatchError("source_patch_workspace_tampered")


def _enforce_store_bounds(store: SourceWorkspaceStore, entries: tuple[SourceFileEntry, ...]) -> None:
    if not entries or len(entries) > store._max_files:
        raise SourcePatchError("source_patch_workspace_bounds")
    total = 0
    for entry in entries:
        if entry.size > store._max_file_bytes:
            raise SourcePatchError("source_patch_workspace_bounds")
        total += entry.size
    if total > store._max_total_bytes:
        raise SourcePatchError("source_patch_workspace_bounds")


def _file_diff(path: str, before: bytes | None, after: bytes | None) -> str:
    before_text = _decode_patch_text(before) if before is not None else ""
    after_text = _decode_patch_text(after) if after is not None else ""
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"before/{path}",
            tofile=f"after/{path}",
            n=3,
            lineterm="\n",
        )
    )
    if not diff and before != after:
        return f"--- before/{path}\n+++ after/{path}\n@@ empty-file-state-change @@\n"
    return diff


def _diff_counts(diff: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _patch_fingerprint(value) -> str:
    try:
        return _fingerprint_value(value)
    except SourceWorkspaceError:
        raise SourcePatchError("source_patch_fingerprint_invalid") from None


def _json_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _json_fingerprint(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


__all__ = [
    "MAX_CHANGED_FILES",
    "MAX_DIFF_BYTES",
    "SourcePatchError",
    "SourcePatchPreview",
    "SourcePatchReceipt",
    "SourcePatchStore",
    "apply_installed_workspace_patch",
    "inspect_installed_module_source",
    "inspect_installed_patch_receipt",
    "preview_installed_workspace_patch",
    "read_installed_workspace_file",
]
