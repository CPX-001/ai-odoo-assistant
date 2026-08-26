"""Install-time initialization for the Odoo-owned Assistant runtime."""

import logging
import os

from .models.assistant_bridge import (
    DEFAULT_TURN_TIMEOUT_SECONDS,
    SECRET_FILE_ENV,
    SECRET_FILE_PARAM,
    SERVICE_URL_ENV,
    SERVICE_URL_PARAM,
    TURN_TIMEOUT_ENV,
    TURN_TIMEOUT_PARAM,
)
from .runtime import RuntimePathError, RuntimePaths
from .services.assistant_client import AssistantServiceClient, AssistantServiceError

LOGGER = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    """Create the local runtime layout and refresh temporary source indexes if configured."""

    try:
        RuntimePaths.from_odoo().ensure()
    except RuntimePathError as error:
        LOGGER.warning("Odoo AI runtime directory initialization failed: %s", error)

    try:
        client = _temporary_source_client(env)
        if client is None:
            return
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


def _temporary_source_client(env):
    """Build the residual source/retrieval client without an Assistant workflow bridge."""

    parameters = env["ir.config_parameter"]
    service_url = parameters._get_param(SERVICE_URL_PARAM) or os.environ.get(SERVICE_URL_ENV)
    if not service_url:
        LOGGER.info("Odoo AI legacy index refresh deferred: service not configured")
        return None
    secret_file = parameters._get_param(SECRET_FILE_PARAM) or os.environ.get(SECRET_FILE_ENV)
    raw_timeout = parameters._get_param(TURN_TIMEOUT_PARAM) or os.environ.get(TURN_TIMEOUT_ENV)
    try:
        timeout = float(raw_timeout) if raw_timeout not in {None, ""} else DEFAULT_TURN_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        timeout = DEFAULT_TURN_TIMEOUT_SECONDS
    if not 0 < timeout <= 300:
        timeout = DEFAULT_TURN_TIMEOUT_SECONDS
    return AssistantServiceClient(
        base_url=service_url,
        shared_secret_file=secret_file,
        timeout=timeout,
    )
