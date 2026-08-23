"""SQLAlchemy repository for current-version knowledge and PostgreSQL FTS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import cast

from odoo_ai.contracts import KnowledgeChunk as KnowledgeChunkData
from odoo_ai.contracts import KnowledgeDocument as KnowledgeDocumentData
from odoo_ai.storage.models import KnowledgeChunk, KnowledgeDocument

_FTS_CONFIG = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentUpsert:
    document_id: UUID
    fingerprint_changed: bool
    chunk_count: int


def upsert_knowledge_document(
    session: Session,
    *,
    instance_profile_id: UUID,
    document: KnowledgeDocumentData,
    chunks: tuple[KnowledgeChunkData, ...],
    fts_config: str,
) -> KnowledgeDocumentUpsert:
    """Insert or transactionally replace one logical document version."""

    _validate_fts_config(fts_config)
    stored = session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.instance_profile_id == instance_profile_id,
            KnowledgeDocument.provider_id == document.provider_id,
            KnowledgeDocument.document_id == document.document_id,
        )
    )
    if stored is not None and stored.fingerprint == document.fingerprint:
        was_retired = stored.status == "retired"
        stored.status = "current"
        stored.observed_at = document.observed_at
        stored.modified_at = document.modified_at
        if not was_retired:
            chunk_count = session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.knowledge_document_id == stored.id
                )
            )
            return KnowledgeDocumentUpsert(
                document_id=stored.id,
                fingerprint_changed=False,
                chunk_count=int(chunk_count or 0),
            )
    elif stored is None:
        stored = KnowledgeDocument(
            instance_profile_id=instance_profile_id,
            provider_id=document.provider_id,
            document_id=document.document_id,
            title=document.title,
            locale=document.locale,
            media_type=document.media_type.value,
            fingerprint=document.fingerprint,
            status="current",
            size_bytes=document.size_bytes,
            observed_at=document.observed_at,
            modified_at=document.modified_at,
        )
        session.add(stored)
        session.flush()
    else:
        stored.title = document.title
        stored.locale = document.locale
        stored.media_type = document.media_type.value
        stored.fingerprint = document.fingerprint
        stored.status = "current"
        stored.size_bytes = document.size_bytes
        stored.observed_at = document.observed_at
        stored.modified_at = document.modified_at

    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == stored.id))
    for chunk in chunks:
        session.add(
            KnowledgeChunk(
                id=_chunk_id(
                    instance_profile_id=instance_profile_id,
                    document=document,
                    chunk=chunk,
                ),
                knowledge_document_id=stored.id,
                ordinal=chunk.ordinal,
                document_fingerprint=document.fingerprint,
                fingerprint=chunk.fingerprint,
                content=chunk.content,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                char_count=chunk.char_count,
                byte_count=chunk.byte_count,
                fts_config=fts_config,
            )
        )
    session.flush()
    session.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.knowledge_document_id == stored.id)
        .values(search_vector=func.to_tsvector(cast(fts_config, REGCONFIG), KnowledgeChunk.content))
    )
    return KnowledgeDocumentUpsert(
        document_id=stored.id,
        fingerprint_changed=True,
        chunk_count=len(chunks),
    )


def retire_missing_knowledge_documents(
    session: Session,
    *,
    instance_profile_id: UUID,
    provider_id: str,
    seen_document_ids: set[str],
) -> int:
    """Retire unseen documents only after a complete provider snapshot."""

    statement = select(KnowledgeDocument).where(
        KnowledgeDocument.instance_profile_id == instance_profile_id,
        KnowledgeDocument.provider_id == provider_id,
        KnowledgeDocument.status == "current",
    )
    if seen_document_ids:
        statement = statement.where(KnowledgeDocument.document_id.not_in(seen_document_ids))
    documents = list(session.scalars(statement))
    for document in documents:
        document.status = "retired"
    session.flush()
    return len(documents)


def get_knowledge_document(
    session: Session,
    *,
    instance_profile_id: UUID,
    provider_id: str,
    document_id: str,
) -> KnowledgeDocument | None:
    return session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.instance_profile_id == instance_profile_id,
            KnowledgeDocument.provider_id == provider_id,
            KnowledgeDocument.document_id == document_id,
        )
    )


def list_knowledge_chunks(session: Session, *, knowledge_document_id: UUID) -> list[KnowledgeChunk]:
    return list(
        session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.knowledge_document_id == knowledge_document_id)
            .order_by(KnowledgeChunk.ordinal)
        )
    )


def _validate_fts_config(fts_config: str) -> None:
    if _FTS_CONFIG.fullmatch(fts_config) is None:
        raise ValueError("invalid PostgreSQL FTS configuration")


def _chunk_id(
    *,
    instance_profile_id: UUID,
    document: KnowledgeDocumentData,
    chunk: KnowledgeChunkData,
) -> UUID:
    identity = ":".join(
        (
            "odoo-ai-knowledge",
            str(instance_profile_id),
            document.provider_id,
            document.document_id,
            document.fingerprint,
            str(chunk.ordinal),
        )
    )
    return uuid5(NAMESPACE_URL, identity)
