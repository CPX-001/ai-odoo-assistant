"""Composition of non-executable Assistant resources contributed by installed providers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .context import ContextProvider, ContextProviderCatalog
from .contracts import CapabilityError
from .provider import CapabilityProvider, discover_odoo_capability_providers
from .registry import CapabilityRegistry, discover_capabilities_for_env
from .skills import SkillCatalog, SkillDefinition


@dataclass(frozen=True, slots=True)
class AssistantExtensionStatus:
    """Sanitized status for one provider's Skill/Context resource layer."""

    provider_id: str
    state: str
    skill_count: int = 0
    context_provider_count: int = 0
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.state not in {"loaded", "failed"}:
            raise CapabilityError("assistant_extension_state_invalid")
        if self.skill_count < 0 or self.context_provider_count < 0:
            raise CapabilityError("assistant_extension_count_invalid")
        if self.state == "loaded" and self.error_code:
            raise CapabilityError("assistant_extension_state_invalid")
        if self.state == "failed" and not self.error_code:
            raise CapabilityError("assistant_extension_state_invalid")


@dataclass(frozen=True, slots=True)
class AssistantExtensionCatalog:
    """Effective declarative resources around the executable capability registry."""

    skills: SkillCatalog
    context_providers: ContextProviderCatalog
    statuses: tuple[AssistantExtensionStatus, ...] = ()


def compose_assistant_extensions(
    providers: Iterable[CapabilityProvider],
    *,
    capability_registry: CapabilityRegistry,
) -> AssistantExtensionCatalog:
    """Compose resources only from capability providers accepted by the host registry.

    A provider whose executable contract failed never gets to contribute instructions or
    context. Resource identity conflicts are also fail-isolated for optional providers.
    Required providers fail closed. This preserves one provider trust decision across the
    executable and non-executable layers without letting Skills become authority.
    """

    ordered = tuple(sorted(providers, key=lambda item: item.provider_id))
    statuses_by_id = {
        item.provider_id: item for item in capability_registry.provider_statuses
    }
    skills: list[SkillDefinition] = []
    contexts: list[ContextProvider] = []
    skill_providers: dict[str, str] = {}
    skill_owners: set[str] = set()
    context_owners: set[str] = set()
    statuses: list[AssistantExtensionStatus] = []

    for provider in ordered:
        capability_status = statuses_by_id.get(provider.provider_id)
        if capability_status is None:
            raise CapabilityError("assistant_extension_provider_unregistered")
        if capability_status.state == "failed":
            statuses.append(
                AssistantExtensionStatus(
                    provider_id=provider.provider_id,
                    state="failed",
                    error_code=capability_status.error_code,
                )
            )
            continue

        error_code = _resource_conflict_code(
            provider,
            skill_owners=skill_owners,
            context_owners=context_owners,
        )
        if error_code:
            if not provider.optional:
                raise CapabilityError(error_code)
            statuses.append(
                AssistantExtensionStatus(
                    provider_id=provider.provider_id,
                    state="failed",
                    error_code=error_code,
                )
            )
            continue

        skills.extend(provider.skills)
        contexts.extend(provider.context_providers)
        for skill in provider.skills:
            skill_owners.add(skill.skill_id)
            skill_providers[skill.skill_id] = provider.provider_id
        context_owners.update(item.provider_id for item in provider.context_providers)
        statuses.append(
            AssistantExtensionStatus(
                provider_id=provider.provider_id,
                state="loaded",
                skill_count=len(provider.skills),
                context_provider_count=len(provider.context_providers),
            )
        )

    return AssistantExtensionCatalog(
        skills=SkillCatalog(skills, skill_providers=skill_providers),
        context_providers=ContextProviderCatalog(contexts),
        statuses=tuple(statuses),
    )


def discover_assistant_extensions_for_env(
    env,
    *,
    capability_registry: CapabilityRegistry | None = None,
) -> AssistantExtensionCatalog:
    """Discover the declarative extension layer from the same effective Odoo registry."""

    registry = capability_registry or discover_capabilities_for_env(env)
    providers = discover_odoo_capability_providers(env)
    if not providers:
        return AssistantExtensionCatalog(
            skills=SkillCatalog(),
            context_providers=ContextProviderCatalog(),
        )
    return compose_assistant_extensions(providers, capability_registry=registry)


def _resource_conflict_code(
    provider: CapabilityProvider,
    *,
    skill_owners: set[str],
    context_owners: set[str],
) -> str:
    if any(item.skill_id in skill_owners for item in provider.skills):
        return "skill_id_duplicate"
    if any(item.provider_id in context_owners for item in provider.context_providers):
        return "context_provider_id_duplicate"
    return ""


__all__ = [
    "AssistantExtensionCatalog",
    "AssistantExtensionStatus",
    "compose_assistant_extensions",
    "discover_assistant_extensions_for_env",
]
