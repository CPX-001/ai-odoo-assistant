"""Replaceable infrastructure adapters for stable service ports."""

from odoo_ai.adapters.context_runtime import load_instance_summary, persist_trace_events
from odoo_ai.adapters.diagnostics_runtime import RuntimeDiagnosticsService
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
    "RuntimeDiagnosticsService",
    "load_instance_summary",
    "persist_trace_events",
]
