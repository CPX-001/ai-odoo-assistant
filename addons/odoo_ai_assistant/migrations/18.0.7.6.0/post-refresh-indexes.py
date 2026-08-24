"""Schedule persistent index refresh when upgrading an existing addon install."""

import logging

from odoo import SUPERUSER_ID, api

LOGGER = logging.getLogger(__name__)


def migrate(cr, version):
    del version
    env = api.Environment(cr, SUPERUSER_ID, {})
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
    except Exception:  # noqa: BLE001 - upgrade remains recoverable if service is degraded
        LOGGER.warning("Odoo AI index refresh deferred during addon upgrade")
