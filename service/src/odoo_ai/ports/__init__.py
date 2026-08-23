"""Stable ports implemented by infrastructure adapters in later milestones."""

from odoo_ai.ports.actions import (
    ActionApprovalStore,
    ActionAuthorityIssuer,
    ActionDecisionOutcome,
    StoredActionProposal,
    StoredDecisionResult,
)
from odoo_ai.ports.knowledge import KnowledgeProvider
from odoo_ai.ports.logs import LogProvider
from odoo_ai.ports.odoo import (
    ModelMetadataGateway,
    OdooActionGateway,
    OdooActionGatewayFactory,
    OdooActionPreviewGateway,
    OdooGateway,
    OdooGatewayError,
    OdooInstanceGateway,
    OdooQueryGateway,
)
from odoo_ai.ports.reasoning import ReasoningEngine

__all__ = [
    "KnowledgeProvider",
    "ActionApprovalStore",
    "ActionAuthorityIssuer",
    "ActionDecisionOutcome",
    "LogProvider",
    "ModelMetadataGateway",
    "OdooGateway",
    "OdooActionGateway",
    "OdooActionGatewayFactory",
    "OdooGatewayError",
    "OdooActionPreviewGateway",
    "OdooInstanceGateway",
    "OdooQueryGateway",
    "ReasoningEngine",
    "StoredActionProposal",
    "StoredDecisionResult",
]
