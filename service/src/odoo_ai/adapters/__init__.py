"""Replaceable infrastructure adapters for stable service ports."""

from odoo_ai.adapters.context_runtime import load_instance_summary, persist_trace_events
from odoo_ai.adapters.odoo_http import (
    HttpOdooGateway,
    HttpOdooInstanceGateway,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
)

__all__ = [
    "HttpOdooGateway",
    "HttpOdooInstanceGateway",
    "OdooGatewayError",
    "OdooGatewayFactory",
    "OdooGatewaySettings",
    "load_instance_summary",
    "persist_trace_events",
]
