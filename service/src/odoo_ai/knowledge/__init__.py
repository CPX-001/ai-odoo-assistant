"""Bounded knowledge ingestion and lexical indexing."""

from odoo_ai.knowledge.chunking import (
    KnowledgeChunkingError,
    KnowledgeChunkLimits,
    chunk_document,
)
from odoo_ai.knowledge.filesystem import (
    KNOWLEDGE_SOURCES_ENV,
    FilesystemKnowledgeLimits,
    FilesystemKnowledgeProvider,
    KnowledgeSourceConfig,
    knowledge_sources_from_env,
)
from odoo_ai.knowledge.ingestion import KnowledgeIngestionService
from odoo_ai.knowledge.sqlalchemy_store import SqlAlchemyKnowledgeIngestStore

__all__ = [
    "KNOWLEDGE_SOURCES_ENV",
    "FilesystemKnowledgeLimits",
    "FilesystemKnowledgeProvider",
    "KnowledgeChunkLimits",
    "KnowledgeChunkingError",
    "KnowledgeIngestionService",
    "KnowledgeSourceConfig",
    "SqlAlchemyKnowledgeIngestStore",
    "chunk_document",
    "knowledge_sources_from_env",
]
