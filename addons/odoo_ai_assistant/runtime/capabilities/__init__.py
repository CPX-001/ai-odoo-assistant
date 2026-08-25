"""Addon-local capability framework.

Add a provider module under :mod:`.providers` and decorate a handler with ``@tool``.
Discovery is automatic; no central import list or Odoo relation is required.
"""

from .contracts import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityResult,
    CapabilityRisk,
    JsonValue,
)
from .decorators import tool
from .executor import CapabilityExecutor
from .registry import CapabilityRegistry, clear_discovery_cache, discover_capabilities

__all__ = [
    "CapabilityContext",
    "CapabilityDefinition",
    "CapabilityEffect",
    "CapabilityError",
    "CapabilityExecutor",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilityRisk",
    "JsonValue",
    "clear_discovery_cache",
    "discover_capabilities",
    "tool",
]
