"""Stable ports implemented by infrastructure adapters in later milestones."""

from odoo_ai.ports.knowledge import KnowledgeProvider
from odoo_ai.ports.logs import LogProvider
from odoo_ai.ports.odoo import (
    ModelMetadataGateway,
    OdooActionPreviewGateway,
    OdooGateway,
    OdooInstanceGateway,
    OdooQueryGateway,
)
from odoo_ai.ports.reasoning import ReasoningEngine

__all__ = [
    "KnowledgeProvider",
    "LogProvider",
    "ModelMetadataGateway",
    "OdooGateway",
    "OdooActionPreviewGateway",
    "OdooInstanceGateway",
    "OdooQueryGateway",
    "ReasoningEngine",
]
