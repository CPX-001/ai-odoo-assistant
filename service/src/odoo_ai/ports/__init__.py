"""Stable ports for responsibilities still hosted by the temporary service."""

from odoo_ai.ports.knowledge import KnowledgeProvider
from odoo_ai.ports.logs import LogProvider
from odoo_ai.ports.odoo import (
    ModelMetadataGateway,
    OdooGateway,
    OdooGatewayError,
    OdooInstanceGateway,
)
from odoo_ai.ports.reasoning import ReasoningEngine, ReasoningEngineError

__all__ = [
    "KnowledgeProvider",
    "LogProvider",
    "ModelMetadataGateway",
    "OdooGateway",
    "OdooGatewayError",
    "OdooInstanceGateway",
    "ReasoningEngine",
    "ReasoningEngineError",
]
