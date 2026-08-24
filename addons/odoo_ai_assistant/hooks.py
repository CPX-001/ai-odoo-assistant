"""Install-time product initialization that delegates heavy work to the Assistant Service."""

import logging

from .services.assistant_client import AssistantServiceError

LOGGER = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    """Build persistent source/knowledge indexes after the addon is installed.

    Odoo only triggers the local service; filesystem scanning and indexing remain
    inside the Assistant Service boundary. Installation is not rolled back when
    the optional reasoning/index service is temporarily unavailable.
    """

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
        LOGGER.warning("Odoo AI initial index refresh deferred: %s", error.code)
    except Exception:  # noqa: BLE001 - install must not leak deployment details
        LOGGER.warning("Odoo AI initial index refresh deferred")
