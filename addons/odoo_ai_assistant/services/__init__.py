"""Odoo-side services used by the embedded runtime."""

from .instance_inventory import InstanceInventoryError, collect_instance_inventory

__all__ = [
    "InstanceInventoryError",
    "collect_instance_inventory",
]
