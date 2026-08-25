"""Odoo query-discovery capabilities migrated from the legacy agent catalog."""

from __future__ import annotations

from datetime import UTC, datetime

from ....services.turn_context import TurnContextError, search_agent_models
from ..contracts import (
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityRisk,
)
from ..decorators import tool


@tool(
    name="odoo.search_models",
    title="Search Odoo models",
    description=(
        "Search the installed Odoo model registry under the effective user. Use this "
        "before guessing model names; discovery itself grants no record authority."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 32},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "models": {
                "type": "array",
                "maxItems": 32,
                "items": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["model", "label"],
                    "additionalProperties": False,
                },
            },
            "captured_at": {"type": "string"},
            "content_trust": {"type": "string", "enum": ["untrusted"]},
        },
        "required": ["models", "captured_at", "content_trust"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "query", "discovery"),
    max_calls=8,
    max_input_bytes=2 * 1024,
    max_output_bytes=32 * 1024,
)
def search_models(context: CapabilityContext, arguments):
    try:
        models = search_agent_models(
            context.env,
            arguments["query"],
            limit=arguments.get("limit", 20),
        )
    except TurnContextError as error:
        raise CapabilityError(error.code) from error
    return {
        "models": models,
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "content_trust": "untrusted",
    }
