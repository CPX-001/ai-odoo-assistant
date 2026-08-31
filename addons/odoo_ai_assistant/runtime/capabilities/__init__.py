"""Addon-local extension framework for agent capabilities.

Core provider modules remain automatically discovered. Trusted installed Odoo addons may
also contribute :class:`CapabilityProvider` markers; every executable operation still
resolves to the same host-owned :class:`CapabilityDefinition` contract.
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
    CapabilityPreview,
    CapabilityResult,
    CapabilityRisk,
    CapabilitySetting,
    CapabilitySettingType,
    CapabilityVerification,
    JsonValue,
)
from .decorators import tool
from .executor import CapabilityExecutor
from .policy import CapabilityPolicy, CapabilityPolicyDecision, ExecutionAuthority
from .provider import (
    CapabilityProvider,
    CapabilityProviderLoader,
    CapabilityProviderStatus,
    discover_odoo_capability_providers,
)
from .registry import (
    CapabilityRegistry,
    clear_discovery_cache,
    compose_capability_registry,
    discover_capabilities,
    discover_capabilities_for_env,
)

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
    "CapabilityPreview",
    "CapabilityProvider",
    "CapabilityProviderLoader",
    "CapabilityProviderStatus",
    "CapabilityRegistry",
    "CapabilityResult",
    "CapabilityRisk",
    "CapabilitySetting",
    "CapabilitySettingType",
    "CapabilityVerification",
    "ExecutionAuthority",
    "JsonValue",
    "clear_discovery_cache",
    "compose_capability_registry",
    "discover_capabilities",
    "discover_capabilities_for_env",
    "discover_odoo_capability_providers",
    "tool",
]
