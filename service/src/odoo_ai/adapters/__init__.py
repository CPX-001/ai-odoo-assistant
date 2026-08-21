"""Replaceable infrastructure adapters for stable service ports."""

from odoo_ai.adapters.odoo_http import (
    HttpOdooGateway,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
)

__all__ = [
    "HttpOdooGateway",
    "OdooGatewayError",
    "OdooGatewayFactory",
    "OdooGatewaySettings",
]
