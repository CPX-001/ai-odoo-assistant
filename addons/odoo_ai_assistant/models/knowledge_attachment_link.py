"""Idempotent link from one temporary chat upload to its persisted Knowledge source."""

from odoo import fields, models


class AssistantKnowledgeAttachmentSourceLink(models.Model):
    _inherit = "odoo.ai.knowledge.attachment"

    knowledge_source_id = fields.Many2one(
        "odoo.ai.knowledge.source",
        readonly=True,
        index=True,
        ondelete="set null",
    )


__all__ = ["AssistantKnowledgeAttachmentSourceLink"]
