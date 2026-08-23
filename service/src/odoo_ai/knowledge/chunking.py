"""Deterministic character/byte bounded document chunking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from odoo_ai.contracts import KnowledgeChunk, KnowledgeDocument


@dataclass(frozen=True, slots=True)
class KnowledgeChunkLimits:
    max_chars: int = 2_000
    max_bytes: int = 8_000
    max_chunks: int = 4096

    def __post_init__(self) -> None:
        values = (self.max_chars, self.max_bytes, self.max_chunks)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("knowledge chunk limits must be positive integers")
        if self.max_chars > 32_768 or self.max_bytes > 65_536 or self.max_chunks > 65_536:
            raise ValueError("knowledge chunk limits exceed contract bounds")


class KnowledgeChunkingError(ValueError):
    """Sanitized failure when a configured chunk budget cannot cover a document."""


def chunk_document(
    document: KnowledgeDocument,
    *,
    limits: KnowledgeChunkLimits | None = None,
) -> tuple[KnowledgeChunk, ...]:
    """Split normalized text reproducibly, preferring complete lines."""

    effective_limits = limits or KnowledgeChunkLimits()
    content = document.content
    chunks: list[KnowledgeChunk] = []
    start = 0
    while start < len(content):
        if len(chunks) >= effective_limits.max_chunks:
            raise KnowledgeChunkingError("knowledge_chunk_limit")
        end = _bounded_end(
            content,
            start=start,
            max_chars=effective_limits.max_chars,
            max_bytes=effective_limits.max_bytes,
        )
        if end < len(content):
            newline = content.rfind("\n", start + 1, end + 1)
            if newline >= start:
                end = newline + 1
        if end <= start:
            raise KnowledgeChunkingError("knowledge_chunk_bounds")
        text = content[start:end]
        ordinal = len(chunks)
        fingerprint_input = (f"{document.fingerprint}\0{ordinal}\0{start}\0{end}\0{text}").encode()
        fingerprint = f"sha256:{hashlib.sha256(fingerprint_input).hexdigest()}"
        chunks.append(
            KnowledgeChunk(
                ordinal=ordinal,
                content=text,
                start_offset=start,
                end_offset=end,
                start_line=content.count("\n", 0, start) + 1,
                end_line=content.count("\n", 0, max(start, end - 1)) + 1,
                fingerprint=fingerprint,
                char_count=len(text),
                byte_count=len(text.encode("utf-8")),
            )
        )
        start = end
    return tuple(chunks)


def _bounded_end(content: str, *, start: int, max_chars: int, max_bytes: int) -> int:
    high = min(len(content), start + max_chars)
    if len(content[start:high].encode("utf-8")) <= max_bytes:
        return high
    low = start + 1
    while low < high:
        middle = (low + high + 1) // 2
        if len(content[start:middle].encode("utf-8")) <= max_bytes:
            low = middle
        else:
            high = middle - 1
    if len(content[start:low].encode("utf-8")) > max_bytes:
        raise KnowledgeChunkingError("knowledge_chunk_byte_limit")
    return low
