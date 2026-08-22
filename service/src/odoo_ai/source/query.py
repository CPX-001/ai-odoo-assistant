"""Bounded structural source queries and fingerprint-checked excerpts."""

from __future__ import annotations

import hashlib
import io
import re
import tokenize
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Final, cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    FindModelExtensionsRequest,
    FindModelExtensionsResult,
    FindSymbolRequest,
    FindSymbolResult,
    ModelExtensionGroup,
    ReadExcerptRequest,
    SourceCandidate,
    SourceExcerpt,
    SourceExcerptLine,
    SourceMatchReason,
    SourceProvenance,
    SourceRef,
)
from odoo_ai.source.scanner import ResolvedSourceRoot
from odoo_ai.storage.source_repository import (
    IndexedSourcePointer,
    IndexedSourceSymbol,
    find_indexed_model_extensions,
    get_indexed_source_pointer,
    search_indexed_source_symbols,
)

MAX_CANDIDATE_POOL: Final = 200
MAX_HASH_BYTES: Final = 2 * 1024 * 1024


class SourceQueryError(RuntimeError):
    """Sanitized source retrieval failure with no physical path disclosure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SourceEvidenceService:
    """Query the current source index and read only refs emitted by it."""

    def __init__(
        self,
        *,
        session: Session,
        roots: tuple[ResolvedSourceRoot, ...],
    ) -> None:
        if not roots:
            raise ValueError("at least one resolved source root is required")
        self._session = session
        self._roots = roots

    def find_symbol(
        self, *, instance_profile_id: UUID, request: FindSymbolRequest
    ) -> FindSymbolResult:
        normalized = _normalize_symbol(request.query)
        if not normalized:
            return FindSymbolResult(candidates=())
        rows = search_indexed_source_symbols(
            self._session,
            instance_profile_id=instance_profile_id,
            query=request.query,
            normalized_query=normalized,
            model=request.model,
            module=request.module,
            limit=MAX_CANDIDATE_POOL,
        )
        candidates = sorted(
            (_matched_candidate(row, request.query) for row in rows),
            key=lambda item: (
                -item.score,
                _kind_priority(item.kind),
                item.module,
                item.logical_path,
                item.start_line,
                str(item.symbol_id),
            ),
        )[: request.max_results]
        return FindSymbolResult(candidates=tuple(candidates))

    def find_model_extensions(
        self,
        *,
        instance_profile_id: UUID,
        request: FindModelExtensionsRequest,
    ) -> FindModelExtensionsResult:
        rows = find_indexed_model_extensions(
            self._session,
            instance_profile_id=instance_profile_id,
            model=request.model,
            module=request.module,
            limit=request.max_results,
        )
        grouped: dict[tuple[str, str, str], list[SourceCandidate]] = defaultdict(list)
        for row in rows:
            grouped[(row.module, row.logical_path, row.provenance)].append(
                _candidate(row, score=100, reason=SourceMatchReason.EXACT)
            )
        groups = tuple(
            ModelExtensionGroup(
                module=module,
                logical_path=logical_path,
                provenance=SourceProvenance(provenance),
                relationships=tuple(relationships),
                runtime_order_checked=False,
            )
            for (module, logical_path, provenance), relationships in sorted(grouped.items())
        )
        return FindModelExtensionsResult(model=request.model, groups=groups)

    def read_excerpt(
        self,
        *,
        instance_profile_id: UUID,
        request: ReadExcerptRequest,
    ) -> SourceExcerpt:
        start_line = cast(int, request.ref.start_line)
        end_line = cast(int, request.ref.end_line)
        pointer = get_indexed_source_pointer(
            self._session,
            instance_profile_id=instance_profile_id,
            source_file_id=request.ref.source_file_id,
            fingerprint=request.ref.fingerprint,
            start_line=start_line,
            end_line=end_line,
        )
        if pointer is None:
            raise SourceQueryError("source_ref_invalid")
        content = self._read_current_file(pointer)
        text = _decode_source(content, pointer.kind)
        lines = _excerpt_lines(
            text,
            start_line=start_line,
            end_line=end_line,
            context_before=request.context_before,
            context_after=request.context_after,
            max_lines=request.max_lines,
            max_bytes=request.max_bytes,
        )
        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.SOURCE,
            status=EvidenceStatus.CHECKED,
            title=f"Source: {pointer.module}/{request.ref.start_line}",
            summary="Fingerprint-checked excerpt from the bounded source index.",
            payload=cast(
                dict[str, Any],
                {
                    "module": pointer.module,
                    "kind": pointer.kind,
                    "trust": "untrusted_source",
                    "lines": [line.model_dump(mode="json") for line in lines],
                },
            ),
            pointer={
                "source_file_id": str(pointer.source_file_id),
                "logical_path": pointer.logical_path,
                "start_line": lines[0].number,
                "end_line": lines[-1].number,
            },
            observed_at=pointer.observed_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=pointer.fingerprint,
        )
        return SourceExcerpt(
            ref=request.ref,
            module=pointer.module,
            logical_path=pointer.logical_path,
            lines=lines,
            evidence=evidence,
        )

    def _read_current_file(self, pointer: IndexedSourcePointer) -> bytes:
        if pointer.size_bytes > MAX_HASH_BYTES:
            raise SourceQueryError("source_too_large")
        path = _resolve_indexed_path(self._roots, pointer.logical_path)
        try:
            before = path.resolve(strict=True)
            content = before.read_bytes()
            after = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise SourceQueryError("source_unavailable") from None
        if before != after or not any(_is_within(after, root.path) for root in self._roots):
            raise SourceQueryError("source_path_escape")
        if len(content) > MAX_HASH_BYTES or len(content) != pointer.size_bytes:
            raise SourceQueryError("stale_source")
        fingerprint = "sha256:" + hashlib.sha256(content).hexdigest()
        if fingerprint != pointer.fingerprint:
            raise SourceQueryError("stale_source")
        return content


def _matched_candidate(row: IndexedSourceSymbol, query: str) -> SourceCandidate:
    tail = row.name.rsplit(".", maxsplit=1)[-1]
    if row.name == query or tail == query:
        return _candidate(row, score=100, reason=SourceMatchReason.EXACT)
    return _candidate(row, score=80, reason=SourceMatchReason.NORMALIZED)


def _candidate(
    row: IndexedSourceSymbol, *, score: int, reason: SourceMatchReason
) -> SourceCandidate:
    ref = SourceRef(
        source_file_id=row.source_file_id,
        fingerprint=row.fingerprint,
        start_line=row.start_line,
        end_line=row.end_line,
    )
    return SourceCandidate(
        symbol_id=row.symbol_id,
        module=row.module,
        kind=row.kind,
        model=row.model,
        name=row.name,
        logical_path=row.logical_path,
        start_line=row.start_line,
        end_line=row.end_line,
        fingerprint=row.fingerprint,
        provenance=SourceProvenance(row.provenance),
        ref=ref,
        score=score,
        match_reason=reason,
        observed_at=row.observed_at,
        details=row.details,
    )


def _normalize_symbol(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _kind_priority(kind: str) -> int:
    return {
        "method": 0,
        "xml_id": 0,
        "model": 1,
        "inherit": 1,
        "field": 2,
        "class": 3,
    }.get(kind, 10)


def _resolve_indexed_path(
    roots: tuple[ResolvedSourceRoot, ...], logical_path: str
) -> Path:
    path = PurePosixPath(logical_path)
    if (
        path.is_absolute()
        or str(path) != logical_path
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SourceQueryError("source_ref_invalid")
    for root in roots:
        candidate = root.path.joinpath(*path.parts)
        try:
            if not candidate.exists():
                continue
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not _is_within(resolved, root.path):
            raise SourceQueryError("source_path_escape")
        if resolved.is_file():
            return candidate
    raise SourceQueryError("source_unavailable")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _decode_source(content: bytes, kind: str) -> str:
    try:
        if kind in {"python", "manifest"}:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
            return content.decode(encoding)
        return content.decode("utf-8-sig")
    except (LookupError, SyntaxError, UnicodeError):
        raise SourceQueryError("source_decode_error") from None


def _excerpt_lines(
    text: str,
    *,
    start_line: int,
    end_line: int,
    context_before: int,
    context_after: int,
    max_lines: int,
    max_bytes: int,
) -> tuple[SourceExcerptLine, ...]:
    source_lines = text.splitlines()
    if start_line < 1 or end_line < start_line or end_line > len(source_lines):
        raise SourceQueryError("source_ref_invalid")
    if end_line - start_line + 1 > max_lines:
        raise SourceQueryError("excerpt_too_large")
    first = max(1, start_line - context_before)
    last = min(len(source_lines), end_line + context_after)
    while last - first + 1 > max_lines:
        if first < start_line:
            first += 1
        elif last > end_line:
            last -= 1
    while _excerpt_byte_size(source_lines, first, last) > max_bytes:
        if first < start_line:
            first += 1
        elif last > end_line:
            last -= 1
        else:
            raise SourceQueryError("excerpt_too_large")
    return tuple(
        SourceExcerptLine(number=number, text=source_lines[number - 1])
        for number in range(first, last + 1)
    )


def _excerpt_byte_size(lines: list[str], first: int, last: int) -> int:
    return sum(
        len(f"{number}:{lines[number - 1]}\n".encode())
        for number in range(first, last + 1)
    )
