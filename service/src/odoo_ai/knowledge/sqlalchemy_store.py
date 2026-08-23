"""SQLAlchemy adapter for the knowledge ingestion store boundary."""

from uuid import UUID

from sqlalchemy.orm import Session

from odoo_ai.contracts import KnowledgeChunk, KnowledgeDocument
from odoo_ai.storage.knowledge_repository import (
    retire_missing_knowledge_documents,
    upsert_knowledge_document,
)


class SqlAlchemyKnowledgeIngestStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        instance_profile_id: UUID,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
        fts_config: str,
    ) -> tuple[bool, int]:
        result = upsert_knowledge_document(
            self._session,
            instance_profile_id=instance_profile_id,
            document=document,
            chunks=chunks,
            fts_config=fts_config,
        )
        return result.fingerprint_changed, result.chunk_count

    def retire_missing(
        self,
        *,
        instance_profile_id: UUID,
        provider_id: str,
        seen_document_ids: set[str],
    ) -> int:
        return retire_missing_knowledge_documents(
            self._session,
            instance_profile_id=instance_profile_id,
            provider_id=provider_id,
            seen_document_ids=seen_document_ids,
        )
