"""Provider-neutral lexical search and fingerprint-checked document excerpts."""

from __future__ import annotations

import re
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    KnowledgeExcerpt,
    KnowledgeExcerptLine,
    KnowledgeReadExcerptRequest,
    KnowledgeRef,
    KnowledgeSearchCandidate,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeStoredChunk,
)


class KnowledgeRetrievalError(RuntimeError):
    """Sanitized recoverable retrieval failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class KnowledgeRetrievalStore(Protocol):
    def search(
        self, *, instance_profile_id: UUID, request: KnowledgeSearchRequest
    ) -> tuple[tuple[KnowledgeStoredChunk, ...], bool]: ...

    def resolve(
        self, *, instance_profile_id: UUID, ref: KnowledgeRef
    ) -> KnowledgeStoredChunk | None: ...


class KnowledgeRetrievalService:
    """Search candidates and promote only revalidated excerpts to Evidence."""

    def __init__(self, *, store: KnowledgeRetrievalStore) -> None:
        self._store = store

    def search(
        self, *, instance_profile_id: UUID, request: KnowledgeSearchRequest
    ) -> KnowledgeSearchResult:
        chunks, truncated = self._store.search(
            instance_profile_id=instance_profile_id,
            request=request,
        )
        candidates = tuple(
            KnowledgeSearchCandidate(
                position=position,
                title=chunk.title,
                provider_id=chunk.ref.provider_id,
                document_id=chunk.ref.document_id,
                locale=chunk.locale,
                media_type=chunk.media_type,
                snippet=_snippet(chunk.content),
                ref=chunk.ref,
            )
            for position, chunk in enumerate(chunks, start=1)
        )
        return KnowledgeSearchResult(candidates=candidates, truncated=truncated)

    def read_excerpt(
        self,
        *,
        instance_profile_id: UUID,
        request: KnowledgeReadExcerptRequest,
    ) -> KnowledgeExcerpt:
        chunk = self._store.resolve(
            instance_profile_id=instance_profile_id,
            ref=request.ref,
        )
        if chunk is None or chunk.ref != request.ref:
            raise KnowledgeRetrievalError("knowledge_ref_stale")
        lines, truncated = _excerpt_lines(
            chunk,
            max_lines=request.max_lines,
            max_chars=request.max_chars,
            max_bytes=request.max_bytes,
        )
        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.DOCUMENT,
            status=EvidenceStatus.CHECKED,
            title=f"Document: {chunk.title}",
            summary="Current fingerprint-checked excerpt from the knowledge index.",
            payload=cast(
                dict[str, Any],
                {
                    "provider_id": chunk.ref.provider_id,
                    "document_id": chunk.ref.document_id,
                    "locale": chunk.locale,
                    "media_type": chunk.media_type.value,
                    "trust": "untrusted_document",
                    "lines": [line.model_dump(mode="json") for line in lines],
                    "truncated": truncated,
                },
            ),
            pointer={
                "provider_id": chunk.ref.provider_id,
                "document_id": chunk.ref.document_id,
                "document_uuid": str(chunk.ref.document_uuid),
                "chunk_uuid": str(chunk.ref.chunk_uuid),
                "ordinal": chunk.ref.ordinal,
                "start_line": lines[0].number,
                "end_line": lines[-1].number,
            },
            observed_at=chunk.observed_at,
            sensitivity=EvidenceSensitivity.NORMAL,
            fingerprint=chunk.ref.document_fingerprint,
        )
        return KnowledgeExcerpt(
            ref=chunk.ref,
            title=chunk.title,
            provider_id=chunk.ref.provider_id,
            document_id=chunk.ref.document_id,
            locale=chunk.locale,
            media_type=chunk.media_type,
            lines=lines,
            truncated=truncated,
            evidence=evidence,
        )


def _snippet(content: str, max_chars: int = 360) -> str:
    normalized = re.sub(r"\s+", " ", content).strip()
    if not normalized:
        raise KnowledgeRetrievalError("knowledge_chunk_empty")
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _excerpt_lines(
    chunk: KnowledgeStoredChunk,
    *,
    max_lines: int,
    max_chars: int,
    max_bytes: int,
) -> tuple[tuple[KnowledgeExcerptLine, ...], bool]:
    source_lines = chunk.content.splitlines()
    if not source_lines:
        source_lines = [chunk.content]
    selected: list[KnowledgeExcerptLine] = []
    used_chars = 0
    used_bytes = 0
    truncated = False
    for offset, source_line in enumerate(source_lines):
        if len(selected) >= max_lines:
            truncated = True
            break
        remaining_chars = max_chars - used_chars
        remaining_bytes = max_bytes - used_bytes
        if remaining_chars <= 0 or remaining_bytes <= 0:
            truncated = True
            break
        line, line_truncated = _bounded_prefix(
            source_line,
            max_chars=remaining_chars,
            max_bytes=remaining_bytes,
        )
        selected.append(KnowledgeExcerptLine(number=chunk.start_line + offset, text=line))
        used_chars += len(line)
        used_bytes += len(line.encode())
        if line_truncated:
            truncated = True
            break
    if not selected:
        raise KnowledgeRetrievalError("knowledge_excerpt_empty")
    if len(selected) < len(source_lines):
        truncated = True
    return tuple(selected), truncated


def _bounded_prefix(value: str, *, max_chars: int, max_bytes: int) -> tuple[str, bool]:
    candidate = value[:max_chars]
    if len(candidate.encode()) <= max_bytes:
        return candidate, len(candidate) < len(value)
    low = 0
    high = len(candidate)
    while low < high:
        middle = (low + high + 1) // 2
        if len(candidate[:middle].encode()) <= max_bytes:
            low = middle
        else:
            high = middle - 1
    return candidate[:low], True
