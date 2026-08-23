"""Incremental ingestion orchestration above provider and storage boundaries."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from odoo_ai.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeScanMetrics,
    KnowledgeScanResult,
)
from odoo_ai.knowledge.chunking import KnowledgeChunkLimits, chunk_document
from odoo_ai.ports import KnowledgeProvider


class KnowledgeIngestStore(Protocol):
    def upsert(
        self,
        *,
        instance_profile_id: UUID,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
        fts_config: str,
    ) -> tuple[bool, int]: ...

    def retire_missing(
        self,
        *,
        instance_profile_id: UUID,
        provider_id: str,
        seen_document_ids: set[str],
    ) -> int: ...


class KnowledgeIngestionService:
    """Persist a complete bounded provider snapshot incrementally."""

    def __init__(
        self,
        *,
        store: KnowledgeIngestStore,
        chunk_limits: KnowledgeChunkLimits | None = None,
        fts_config: str = "simple",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._chunk_limits = chunk_limits or KnowledgeChunkLimits()
        self._fts_config = fts_config
        self._clock = clock

    def ingest(
        self, *, instance_profile_id: UUID, provider: KnowledgeProvider
    ) -> KnowledgeScanResult:
        started = self._clock()
        snapshot = provider.scan()
        indexed = 0
        unchanged = 0
        chunks = 0
        seen_ids: set[str] = set()
        for document in snapshot.documents:
            prepared_chunks = chunk_document(document, limits=self._chunk_limits)
            changed, stored_chunks = self._store.upsert(
                instance_profile_id=instance_profile_id,
                document=document,
                chunks=prepared_chunks,
                fts_config=self._fts_config,
            )
            seen_ids.add(document.document_id)
            chunks += stored_chunks
            if changed:
                indexed += 1
            else:
                unchanged += 1
        retired = 0
        if snapshot.complete:
            retired = self._store.retire_missing(
                instance_profile_id=instance_profile_id,
                provider_id=snapshot.provider_id,
                seen_document_ids=seen_ids,
            )
        duration_ms = max(0, round((self._clock() - started) * 1000))
        return KnowledgeScanResult(
            metrics=KnowledgeScanMetrics(
                documents_seen=len(snapshot.documents),
                documents_indexed=indexed,
                documents_unchanged=unchanged,
                documents_retired=retired,
                errors=len(snapshot.issues),
                chunks=chunks,
                duration_ms=duration_ms,
            ),
            issue_codes=tuple(sorted({issue.code for issue in snapshot.issues}))[:256],
            complete=snapshot.complete,
        )
