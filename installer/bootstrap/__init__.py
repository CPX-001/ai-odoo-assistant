"""Idempotent bootstrap foundation for the supported Linux host."""

from installer.bootstrap.bootstrap import (
    BootstrapError,
    BootstrapPaths,
    Bootstrapper,
    BootstrapResult,
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
    select_odoo_config,
    select_odoo_service,
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
    "SystemAccountManager",
    "discover_linux_host",
    "discover_odoo_services",
    "parse_odoo_config",
    "select_odoo_config",
    "select_odoo_service",
]
