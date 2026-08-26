"""Stable ports for residual Source/Retrieval/Diagnostics responsibilities."""

from odoo_ai.ports.knowledge import KnowledgeProvider
from odoo_ai.ports.logs import LogProvider
from odoo_ai.ports.odoo import OdooGatewayError, OdooInstanceGateway

__all__ = [
    "KnowledgeProvider",
    "LogProvider",
    "OdooGatewayError",
    "OdooInstanceGateway",
]
