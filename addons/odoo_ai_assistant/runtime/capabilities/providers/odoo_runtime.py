"""Built-in Odoo runtime introspection capability."""

from __future__ import annotations

from ..contracts import CapabilityContext, CapabilityEffect, CapabilityRisk
from ..decorators import tool

_EMPTY_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@tool(
    name="odoo.runtime_identity",
    description=(
        "Return the effective Odoo database, user and active company identity bound "
        "to this assistant turn. This is metadata only and grants no extra authority."
    ),
    input_schema=_EMPTY_OBJECT_SCHEMA,
    output_schema={
        "type": "object",
        "properties": {
            "database": {"type": "string"},
            "uid": {"type": "integer"},
            "company_id": {"type": "integer"},
            "allowed_company_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "maxItems": 32,
            },
        },
        "required": ["database", "uid", "company_id", "allowed_company_ids"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.METADATA,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "runtime", "identity"),
    max_calls=2,
)
def runtime_identity(context: CapabilityContext, arguments):
    del arguments
    env = context.env
    if getattr(env, "su", True):
        raise RuntimeError("superuser_context_forbidden")
    return {
        "database": env.cr.dbname,
        "uid": env.uid,
        "company_id": env.company.id,
        "allowed_company_ids": list(env.companies.ids),
    }
