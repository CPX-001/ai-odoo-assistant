"""Install-time initialization for the Odoo-owned Assistant runtime."""

import logging

from .runtime import RuntimePathError, RuntimePaths

LOGGER = logging.getLogger(__name__)
_CONNECTION_PARAMETER = "odoo_ai_assistant.codex_connection_enabled"


def post_init_hook(env) -> None:
    """Initialize the local runtime and require explicit Codex activation on new DBs."""

    env["ir.config_parameter"].set_param(_CONNECTION_PARAMETER, "false")

    try:
        RuntimePaths.from_odoo().ensure()
    except RuntimePathError as error:
        LOGGER.warning("Odoo AI runtime directory initialization failed: %s", error)
