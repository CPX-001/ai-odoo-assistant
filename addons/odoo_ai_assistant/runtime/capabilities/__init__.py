"""Addon-local extension framework for agent capabilities.

Core provider modules remain automatically discovered. Trusted installed Odoo addons may
also contribute :class:`CapabilityProvider` markers; every executable operation still
resolves to the same host-owned :class:`CapabilityDefinition` contract.
"""

from .config import CapabilityConfigResolver
from .context import (
    ContextCollector,
    ContextContribution,
    ContextProvider,
    ContextProviderCatalog,
    ContextProviderStatus,
)
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
from .disclosure import (
    CapabilityDisclosureSnapshot,
    DisclosurePolicy,
    build_disclosure_snapshot,
)
from .executor import CapabilityExecutor
from .extensions import (
    ActiveAssistantExtensions,
    AssistantExtensionCatalog,
    AssistantExtensionStatus,
    compose_assistant_extensions,
    discover_assistant_extensions_for_env,
)
from .features import (
    ProviderFeature,
    ProviderFeatureState,
    ProviderFeatureSupport,
    ProviderProfile,
)
from .manifest import (
    EffectiveAssistantManifest,
    TechnicalAccessProfile,
    build_effective_assistant_manifest,
    technical_access_profile_for_env,
)
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
from .skills import SkillCatalog, SkillDefinition, selector_matches

__all__ = [
    "ActiveAssistantExtensions",
    "AssistantExtensionCatalog",
    "AssistantExtensionStatus",
    "CapabilityApproval",
    "CapabilityConfigResolver",
    "CapabilityContext",
    "CapabilityDefinition",
    "CapabilityDependency",
    "CapabilityDisclosureSnapshot",
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
    "ContextCollector",
    "ContextContribution",
    "ContextProvider",
    "ContextProviderCatalog",
    "ContextProviderStatus",
    "DisclosurePolicy",
    "EffectiveAssistantManifest",
    "ExecutionAuthority",
    "JsonValue",
    "ProviderFeature",
    "ProviderFeatureState",
    "ProviderFeatureSupport",
    "ProviderProfile",
    "SkillCatalog",
    "SkillDefinition",
    "TechnicalAccessProfile",
    "build_disclosure_snapshot",
    "build_effective_assistant_manifest",
    "clear_discovery_cache",
    "compose_assistant_extensions",
    "compose_capability_registry",
    "discover_assistant_extensions_for_env",
    "discover_capabilities",
    "discover_capabilities_for_env",
    "discover_odoo_capability_providers",
    "selector_matches",
    "technical_access_profile_for_env",
    "tool",
]
