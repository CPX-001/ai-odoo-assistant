"""Addon-local extension framework for agent capabilities.

Add a provider module under :mod:`.providers` and decorate a handler with ``@tool``.
Discovery is automatic; registration, policy metadata and transport descriptors come
from the same definition.
"""

from .config import CapabilityConfigResolver
from .contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityDependency,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityResult,
    CapabilityRisk,
    CapabilitySetting,
    CapabilitySettingType,
    JsonValue,
)
from .decorators import tool
from .executor import CapabilityExecutor
from .policy import CapabilityPolicy, CapabilityPolicyDecision, ExecutionAuthority
from .registry import CapabilityRegistry, clear_discovery_cache, discover_capabilities

__all__ = [
    "CapabilityApproval",
    "CapabilityConfigResolver",
    "CapabilityContext",
    "CapabilityDefinition",
    "CapabilityDependency",
    "CapabilityEffect",
    "CapabilityError",
    "CapabilityExecutor",
    "CapabilityExposure",
    "CapabilityPolicy",
    "CapabilityPolicyDecision",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilityRisk",
    "CapabilitySetting",
    "CapabilitySettingType",
    "ExecutionAuthority",
    "JsonValue",
    "clear_discovery_cache",
    "discover_capabilities",
    "tool",
]
