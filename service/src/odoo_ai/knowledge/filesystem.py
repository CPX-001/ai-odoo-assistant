"""Filesystem knowledge provider restricted to explicitly configured roots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from odoo_ai.contracts import (
    KnowledgeDocument,
    KnowledgeMediaType,
    KnowledgeProviderIssue,
    KnowledgeProviderResult,
)

KNOWLEDGE_SOURCES_ENV = "ODOO_AI_KNOWLEDGE_SOURCES"
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_LOCALE = re.compile(r"^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*$")
_SUPPORTED_SUFFIXES = {
    ".md": KnowledgeMediaType.MARKDOWN,
    ".markdown": KnowledgeMediaType.MARKDOWN,
    ".txt": KnowledgeMediaType.TEXT,
}


@dataclass(frozen=True, slots=True)
class KnowledgeSourceConfig:
    """Administrator-owned source configuration kept outside model inputs."""

    provider_id: str
    root: Path
    locale: str | None = None

    def __post_init__(self) -> None:
        if _PROVIDER_ID.fullmatch(self.provider_id) is None:
            raise ValueError("invalid knowledge provider id")
        if not self.root.is_absolute() or ".." in self.root.parts:
            raise ValueError("knowledge root must be absolute and normalized")
        if self.locale is not None and _LOCALE.fullmatch(self.locale) is None:
            raise ValueError("invalid knowledge locale")


@dataclass(frozen=True, slots=True)
class FilesystemKnowledgeLimits:
    max_documents: int = 1024
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_seconds: float = 30.0
    max_depth: int = 16
    excluded_directories: frozenset[str] = frozenset(
        {".git", ".hg", ".svn", "__pycache__", "node_modules"}
    )

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_documents,
            self.max_file_bytes,
            self.max_total_bytes,
            self.max_depth,
        )
        if any(type(value) is not int or value <= 0 for value in integer_limits):
            raise ValueError("knowledge integer limits must be positive")
        if self.max_documents > 4096 or self.max_file_bytes > 2 * 1024 * 1024:
            raise ValueError("knowledge limits exceed contract bounds")
        if not isinstance(self.max_seconds, (int, float)) or self.max_seconds <= 0:
            raise ValueError("knowledge time limit must be positive")


def knowledge_sources_from_env(
    environ: Mapping[str, str] | None = None,
) -> tuple[KnowledgeSourceConfig, ...]:
    """Parse an explicit JSON override; no host paths are guessed."""

    source = os.environ if environ is None else environ
    raw = source.get(KNOWLEDGE_SOURCES_ENV, "")
    if not raw:
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("knowledge sources override must be a JSON list") from None
    if not isinstance(values, list) or len(values) > 128:
        raise ValueError("knowledge sources override must be a bounded JSON list")
    configs: list[KnowledgeSourceConfig] = []
    for value in values:
        if not isinstance(value, dict) or set(value) - {"provider_id", "root", "locale"}:
            raise ValueError("knowledge source contains unsupported fields")
        provider_id = value.get("provider_id")
        root = value.get("root")
        locale = value.get("locale")
        if (
            not isinstance(provider_id, str)
            or not isinstance(root, str)
            or not root
            or len(root) > 4096
            or root != root.strip()
            or (locale is not None and (not isinstance(locale, str) or len(locale) > 64))
        ):
            raise ValueError("knowledge source fields are invalid")
        configs.append(
            KnowledgeSourceConfig(
                provider_id=provider_id,
                root=Path(root),
                locale=locale,
            )
        )
    provider_ids = [config.provider_id for config in configs]
    if len(provider_ids) != len(set(provider_ids)):
        raise ValueError("knowledge provider ids must be unique")
    return tuple(configs)


class FilesystemKnowledgeProvider:
    """Read UTF-8 text/Markdown below one validated configured root."""

    def __init__(
        self,
        config: KnowledgeSourceConfig,
        *,
        limits: FilesystemKnowledgeLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._limits = limits or FilesystemKnowledgeLimits()
        self._clock = clock

    def scan(self) -> KnowledgeProviderResult:
        started = self._clock()
        scanned_at = datetime.now(UTC)
        documents: list[KnowledgeDocument] = []
        issues: list[KnowledgeProviderIssue] = []
        total_bytes = 0
        complete = True

        root = self._validated_root()
        if root is None:
            return KnowledgeProviderResult(
                provider_id=self._config.provider_id,
                documents=(),
                issues=(KnowledgeProviderIssue(code="root_unavailable"),),
                complete=False,
                scanned_at=scanned_at,
            )

        stop = False
        for directory, directory_names, file_names in os.walk(root, followlinks=False):
            current = Path(directory)
            relative_directory = current.relative_to(root)
            depth = len(relative_directory.parts)
            if self._clock() - started > self._limits.max_seconds:
                issues.append(KnowledgeProviderIssue(code="scan_time_limit"))
                complete = False
                break
            retained_directories: list[str] = []
            for name in sorted(directory_names):
                candidate = current / name
                logical_id = (relative_directory / name).as_posix()
                if name in self._limits.excluded_directories:
                    continue
                if candidate.is_symlink():
                    issues.append(
                        KnowledgeProviderIssue(code="symlink_rejected", document_id=logical_id)
                    )
                    continue
                if depth + 1 > self._limits.max_depth:
                    issues.append(
                        KnowledgeProviderIssue(code="depth_limit", document_id=logical_id)
                    )
                    complete = False
                    continue
                retained_directories.append(name)
            directory_names[:] = retained_directories

            for name in sorted(file_names):
                if self._clock() - started > self._limits.max_seconds:
                    issues.append(KnowledgeProviderIssue(code="scan_time_limit"))
                    complete = False
                    stop = True
                    break
                candidate = current / name
                logical_id = (relative_directory / name).as_posix()
                media_type = _SUPPORTED_SUFFIXES.get(candidate.suffix.casefold())
                if media_type is None:
                    continue
                if len(documents) >= self._limits.max_documents:
                    issues.append(KnowledgeProviderIssue(code="document_limit"))
                    complete = False
                    stop = True
                    break
                try:
                    content, modified_at = self._read_text_file(
                        root=root,
                        path=candidate,
                        logical_id=logical_id,
                    )
                except _ProviderFileError as error:
                    issues.append(KnowledgeProviderIssue(code=error.code, document_id=logical_id))
                    continue
                content_bytes = content.encode("utf-8")
                if total_bytes + len(content_bytes) > self._limits.max_total_bytes:
                    issues.append(KnowledgeProviderIssue(code="total_bytes_limit"))
                    complete = False
                    stop = True
                    break
                total_bytes += len(content_bytes)
                title = _document_title(logical_id, content, media_type)
                fingerprint = _document_fingerprint(
                    title=title,
                    locale=self._config.locale,
                    media_type=media_type,
                    content=content,
                )
                documents.append(
                    KnowledgeDocument(
                        provider_id=self._config.provider_id,
                        document_id=logical_id,
                        title=title,
                        locale=self._config.locale,
                        media_type=media_type,
                        content=content,
                        fingerprint=fingerprint,
                        size_bytes=len(content_bytes),
                        observed_at=scanned_at,
                        modified_at=modified_at,
                    )
                )
            if stop:
                break

        return KnowledgeProviderResult(
            provider_id=self._config.provider_id,
            documents=tuple(documents),
            issues=tuple(issues),
            complete=complete,
            scanned_at=scanned_at,
        )

    def _validated_root(self) -> Path | None:
        root = self._config.root
        try:
            if root.is_symlink():
                return None
            resolved = root.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not resolved.is_dir():
            return None
        return resolved

    def _read_text_file(self, *, root: Path, path: Path, logical_id: str) -> tuple[str, datetime]:
        del logical_id
        if path.is_symlink():
            raise _ProviderFileError("symlink_rejected")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except ValueError:
            raise _ProviderFileError("path_escape_rejected") from None
        except (OSError, RuntimeError):
            raise _ProviderFileError("file_unavailable") from None

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(resolved, flags)
        except OSError:
            raise _ProviderFileError("file_unavailable") from None
        try:
            try:
                descriptor_target = Path(f"/proc/self/fd/{descriptor}").resolve(strict=True)
                descriptor_target.relative_to(root)
            except ValueError:
                raise _ProviderFileError("path_escape_rejected") from None
            except (OSError, RuntimeError):
                raise _ProviderFileError("file_unavailable") from None
            stat = os.fstat(descriptor)
            if stat.st_size > self._limits.max_file_bytes:
                raise _ProviderFileError("file_bytes_limit")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(self._limits.max_file_bytes + 1)
        finally:
            os.close(descriptor)
        if len(raw) > self._limits.max_file_bytes:
            raise _ProviderFileError("file_bytes_limit")
        if b"\0" in raw:
            raise _ProviderFileError("binary_ignored")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise _ProviderFileError("binary_ignored") from None
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if not content.strip():
            raise _ProviderFileError("empty_document_ignored")
        normalized_bytes = content.encode("utf-8")
        if len(normalized_bytes) > self._limits.max_file_bytes:
            raise _ProviderFileError("file_bytes_limit")
        return content, datetime.fromtimestamp(stat.st_mtime, tz=UTC)


class _ProviderFileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _document_title(logical_id: str, content: str, media_type: KnowledgeMediaType) -> str:
    if media_type is KnowledgeMediaType.MARKDOWN:
        for line in content.splitlines()[:64]:
            match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if match:
                heading = match.group(1).strip()
                if heading:
                    return heading[:512]
    fallback = Path(logical_id).stem.strip() or logical_id
    return fallback[:512]


def _document_fingerprint(
    *, title: str, locale: str | None, media_type: KnowledgeMediaType, content: str
) -> str:
    canonical = json.dumps(
        {
            "content": content,
            "locale": locale,
            "media_type": media_type.value,
            "title": title,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
