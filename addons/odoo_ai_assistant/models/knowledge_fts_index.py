"""Database-local FTS index for lexical Knowledge retrieval."""

from odoo import models


class AssistantKnowledgeChunkFtsIndex(models.Model):
    _inherit = "odoo.ai.knowledge.chunk"

    def init(self):
        self.env.cr.execute(
            """
            CREATE INDEX IF NOT EXISTS odoo_ai_knowledge_chunk_fts_idx
                ON odoo_ai_knowledge_chunk
             USING GIN (
                 to_tsvector('simple'::regconfig, COALESCE(content, ''))
             )
            """
        )


__all__ = ["AssistantKnowledgeChunkFtsIndex"]
