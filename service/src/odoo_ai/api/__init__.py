"""HTTP API for the local Assistant Service."""

from typing import Any

from fastapi import FastAPI

from odoo_ai.api.app import app as app
from odoo_ai.api.app import create_app as _base_create_app
from odoo_ai.api.configuration import install_configuration_routes
from odoo_ai.runtime.configuration import RuntimeConfigurationService


def create_app(
    *,
    configuration_service: RuntimeConfigurationService | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Build the core API plus the isolated M7 administrative config boundary."""

    return install_configuration_routes(
        _base_create_app(**kwargs),
        service=configuration_service,
    )


install_configuration_routes(app)

__all__ = ["app", "create_app"]
