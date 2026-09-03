"""Phase 10 Technical Odoo/PostgreSQL diagnostics that need no host privilege broker."""

from __future__ import annotations

import re

from odoo.exceptions import AccessError

from ..contracts import (
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityRisk,
)
from ..decorators import tool

_TECHNICAL_GROUPS = ("base.group_system",)
_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")

_MODULE_INPUT = {
    "type": "object",
    "properties": {
        "module": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,127}$"},
    },
    "required": ["module"],
    "additionalProperties": False,
}
_MODULE_OUTPUT = {
    "type": "object",
    "properties": {
        "module": {"type": "string"},
        "display_name": {"type": "string"},
        "summary": {"type": ["string", "null"]},
        "state": {"type": "string"},
        "database_version": {"type": ["string", "null"]},
        "source_version": {"type": ["string", "null"]},
        "author": {"type": ["string", "null"]},
        "license": {"type": ["string", "null"]},
        "application": {"type": "boolean"},
        "dependencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "state": {"type": "string"},
                },
                "required": ["name", "state"],
                "additionalProperties": False,
            },
            "maxItems": 64,
        },
    },
    "required": [
        "module",
        "display_name",
        "summary",
        "state",
        "database_version",
        "source_version",
        "author",
        "license",
        "application",
        "dependencies",
    ],
    "additionalProperties": False,
}
_POSTGRES_OUTPUT = {
    "type": "object",
    "properties": {
        "server_version": {"type": "string"},
        "database_size_bytes": {"type": "integer", "minimum": 0},
        "backend_count": {"type": "integer", "minimum": 0},
        "active_backend_count": {"type": "integer", "minimum": 0},
        "waiting_backend_count": {"type": "integer", "minimum": 0},
    },
    "required": [
        "server_version",
        "database_size_bytes",
        "backend_count",
        "active_backend_count",
        "waiting_backend_count",
    ],
    "additionalProperties": False,
}


def _module_record(context: CapabilityContext, arguments):
    name = arguments.get("module")
    if not isinstance(name, str) or _MODULE_RE.fullmatch(name) is None:
        raise CapabilityError("module_name_invalid")
    try:
        module = context.env["ir.module.module"].search([("name", "=", name)], limit=1)
        if module:
            module.check_access("read")
    except AccessError:
        raise CapabilityError("access_denied") from None
    except Exception:
        raise CapabilityError("module_inspection_failed") from None
    if not module:
        raise CapabilityError("module_not_found")
    return module


@tool(
    name="odoo.module.inspect",
    title="Inspect an installed Odoo module",
    description=(
        "Inspect one Odoo module known to the CURRENT installation. Technical users only. "
        "Returns current registry/database state and bounded manifest metadata; it does not "
        "install, upgrade or run module methods."
    ),
    input_schema=_MODULE_INPUT,
    output_schema=_MODULE_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("odoo", "technical", "module", "inspect"),
    max_calls=8,
    timeout_seconds=5,
)
def module_inspect(context: CapabilityContext, arguments):
    module = _module_record(context, arguments)
    dependencies = []
    for dependency in module.dependencies_id[:64]:
        dependencies.append(
            {
                "name": dependency.name,
                "state": dependency.state or "unknown",
            }
        )
    return {
        "module": module.name,
        "display_name": module.shortdesc or module.name,
        "summary": module.summary or None,
        "state": module.state,
        # Odoo 18 field names are historically inverted: latest_version is the
        # installed DB version, installed_version is the version available on disk.
        "database_version": module.latest_version or None,
        "source_version": module.installed_version or None,
        "author": module.author or None,
        "license": module.license or None,
        "application": bool(module.application),
        "dependencies": dependencies,
    }


@tool(
    name="postgres.health",
    title="Inspect PostgreSQL health",
    description=(
        "Return bounded read-only health facts for the CURRENT Odoo database using fixed "
        "host-owned SQL. Technical users only. No query text, arbitrary SQL or mutation is "
        "accepted."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    output_schema=_POSTGRES_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    required_groups=_TECHNICAL_GROUPS,
    tags=("postgres", "technical", "diagnostic", "health"),
    max_calls=6,
    timeout_seconds=5,
)
def postgres_health(context: CapabilityContext, arguments):
    del arguments
    cr = context.env.cr
    try:
        cr.execute(
            """
            SELECT current_setting('server_version'),
                   pg_database_size(current_database())
            """
        )
        version, database_size = cr.fetchone()
        cr.execute(
            """
            SELECT count(*)::bigint,
                   count(*) FILTER (WHERE state = 'active')::bigint,
                   count(*) FILTER (WHERE wait_event_type IS NOT NULL)::bigint
              FROM pg_stat_activity
             WHERE datname = current_database()
            """
        )
        backend_count, active_count, waiting_count = cr.fetchone()
    except Exception:
        raise CapabilityError("postgres_diagnostic_unavailable") from None
    return {
        "server_version": str(version)[:80],
        "database_size_bytes": max(0, int(database_size)),
        "backend_count": max(0, int(backend_count)),
        "active_backend_count": max(0, int(active_count)),
        "waiting_backend_count": max(0, int(waiting_count)),
    }


__all__ = ["module_inspect", "postgres_health"]
