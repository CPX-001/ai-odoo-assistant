"""Install-time initialization for the Odoo-owned Assistant runtime."""

import logging

from .runtime import RuntimePathError, RuntimePaths
from .services.assistant_client import AssistantServiceError

LOGGER = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    """Create the local runtime layout and defer expensive initialization safely.

    During the architectural migration the existing Assistant Service refresh is
    kept as a compatibility bridge. The Odoo-owned runtime directory is created
    unconditionally so Codex and later embedded scanners never need /opt, /etc,
    /var/lib, root privileges, or a second Unix identity.
    """

    try:
        RuntimePaths.from_odoo().ensure()
    except RuntimePathError as error:
        LOGGER.warning("Odoo AI runtime directory initialization failed: %s", error)

    try:
        client = env["odoo.ai.assistant.bridge"]._client()
        client.source_rescan()
        client.maintenance_knowledge_reindex(
            {
                "actor": {
                    "odoo_uid": env.uid,
                    "odoo_database": env.cr.dbname,
                }
            }
        )
    except AssistantServiceError as error:
        LOGGER.info("Odoo AI legacy index refresh deferred: %s", error.code)
    except Exception:  # noqa: BLE001 - install must not leak deployment details
        LOGGER.info("Odoo AI legacy index refresh deferred")
