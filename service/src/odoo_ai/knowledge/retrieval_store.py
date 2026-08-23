"""SQLAlchemy adapter for the provider-neutral knowledge retrieval store."""

from uuid import UUID

from sqlalchemy.orm import Session

from odoo_ai.contracts import (
    KnowledgeRef,
    KnowledgeSearchRequest,
    KnowledgeStoredChunk,
)
from odoo_ai.storage import (
    get_current_knowledge_chunk,
    search_current_knowledge_chunks,
)


class SqlAlchemyKnowledgeRetrievalStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self, *, instance_profile_id: UUID, request: KnowledgeSearchRequest
    ) -> tuple[tuple[KnowledgeStoredChunk, ...], bool]:
        result = search_current_knowledge_chunks(
            self._session,
            instance_profile_id=instance_profile_id,
            request=request,
        )
        return result.chunks, result.truncated

    def resolve(
        self, *, instance_profile_id: UUID, ref: KnowledgeRef
    ) -> KnowledgeStoredChunk | None:
        validated = KnowledgeRef.model_validate(ref)
        return get_current_knowledge_chunk(
            self._session,
            instance_profile_id=instance_profile_id,
            ref=validated,
        )
