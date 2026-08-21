"""Stable ports implemented by infrastructure adapters in later milestones."""

from odoo_ai.ports.logs import LogProvider
from odoo_ai.ports.odoo import OdooGateway
from odoo_ai.ports.reasoning import ReasoningEngine

__all__ = ["LogProvider", "OdooGateway", "ReasoningEngine"]
