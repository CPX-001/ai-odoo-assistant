"""Idempotent bootstrap foundation for the supported Linux host."""

from installer.bootstrap.bootstrap import (
    BootstrapError,
    BootstrapPaths,
    Bootstrapper,
    BootstrapResult,
    ServiceSettings,
    SystemAccountManager,
)
from installer.bootstrap.discovery import (
    DiscoveryError,
    LinuxHost,
    OdooDeployment,
    OdooService,
    discover_linux_host,
    discover_odoo_services,
    parse_odoo_config,
    resolve_odoo_deployment,
    select_odoo_config,
    select_odoo_service,
)
from installer.bootstrap.postgres import (
    PostgresBootstrapper,
    PostgresBootstrapResult,
    PostgresSettings,
)

__all__ = [
    "BootstrapError",
    "BootstrapPaths",
    "BootstrapResult",
    "Bootstrapper",
    "DiscoveryError",
    "LinuxHost",
    "OdooDeployment",
    "OdooService",
    "ServiceSettings",
    "SystemAccountManager",
    "PostgresBootstrapResult",
    "PostgresBootstrapper",
    "PostgresSettings",
    "discover_linux_host",
    "discover_odoo_services",
    "parse_odoo_config",
    "resolve_odoo_deployment",
    "select_odoo_config",
    "select_odoo_service",
]
