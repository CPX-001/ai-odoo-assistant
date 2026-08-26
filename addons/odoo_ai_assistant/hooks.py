"""Install-time initialization for the Odoo-owned Assistant runtime."""

import logging

from .runtime import RuntimePathError, RuntimePaths

LOGGER = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    """Create the bounded local runtime layout under the real Odoo data directory."""

    del env

    try:
        RuntimePaths.from_odoo().ensure()
    except RuntimePathError as error:
        LOGGER.warning("Odoo AI runtime directory initialization failed: %s", error)
