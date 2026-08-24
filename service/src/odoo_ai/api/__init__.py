"""HTTP API for the local Assistant Service."""

from typing import Any

from fastapi import FastAPI

from odoo_ai.api.admin_diagnostics import install_admin_diagnostics_routes
from odoo_ai.api.agent import AgentServiceFactory, install_agent_routes
from odoo_ai.api.app import app as app
from odoo_ai.api.app import create_app as _base_create_app
from odoo_ai.api.chat import install_chat_routes
from odoo_ai.api.configuration import install_configuration_routes
from odoo_ai.api.maintenance import install_maintenance_routes
from odoo_ai.application.general_chat import GeneralChatService
from odoo_ai.runtime.admin_diagnostics import RuntimeAdminDiagnosticsService
from odoo_ai.runtime.chat import RuntimeChatHistoryService
from odoo_ai.runtime.configuration import RuntimeConfigurationService
from odoo_ai.runtime.maintenance import RuntimeMaintenanceService


def create_app(
    *,
    configuration_service: RuntimeConfigurationService | None = None,
    admin_diagnostics_service: RuntimeAdminDiagnosticsService | None = None,
    maintenance_service: RuntimeMaintenanceService | None = None,
    chat_history_service: RuntimeChatHistoryService | None = None,
    general_chat_service: GeneralChatService | None = None,
    agent_service_factory: AgentServiceFactory | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Build the core API plus isolated administrative and chat boundaries."""

    application = install_configuration_routes(
        _base_create_app(**kwargs),
        service=configuration_service,
    )
    application = install_admin_diagnostics_routes(
        application,
        service=admin_diagnostics_service,
    )
    application = install_maintenance_routes(
        application,
        service=maintenance_service,
    )
    application = install_agent_routes(
        application,
        factory=agent_service_factory,
    )
    return install_chat_routes(
        application,
        history_service=chat_history_service,
        general_service=general_chat_service,
    )


install_configuration_routes(app)
install_admin_diagnostics_routes(app)
install_maintenance_routes(app)
install_agent_routes(app)
install_chat_routes(app)

__all__ = ["app", "create_app"]
