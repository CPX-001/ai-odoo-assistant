"""Odoo-side services shared by current runtime and residual service boundaries."""

from .assistant_client import AssistantServiceClient, AssistantServiceError
from .instance_inventory import InstanceInventoryError, collect_instance_inventory

__all__ = [
    "AssistantServiceClient",
    "AssistantServiceError",
    "InstanceInventoryError",
    "collect_instance_inventory",
]
