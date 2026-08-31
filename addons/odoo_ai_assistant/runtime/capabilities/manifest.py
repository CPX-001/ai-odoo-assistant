"""Effective Assistant self-description derived from host-known runtime state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from .context import ContextProviderCatalog
from .contracts import CapabilityContext, CapabilityError, JsonValue
from .disclosure import CapabilityDisclosureSnapshot, build_disclosure_snapshot
from .features import ProviderProfile
from .registry import CapabilityRegistry
from .skills import SkillCatalog


class TechnicalAccessProfile(StrEnum):
    BUSINESS = "business"
    DEVELOPER = "developer"


@dataclass(frozen=True, slots=True)
class EffectiveAssistantManifest:
    provider: Mapping[str, JsonValue]
    technical_profile: TechnicalAccessProfile
    skills: tuple[Mapping[str, JsonValue], ...]
    capabilities: tuple[Mapping[str, JsonValue], ...]
    context_providers: tuple[Mapping[str, JsonValue], ...]
    evidence_provider_ids: tuple[str, ...] = ()
    configuration_health: tuple[Mapping[str, JsonValue], ...] = ()
    unavailable_features: tuple[Mapping[str, JsonValue], ...] = ()
    disclosure: CapabilityDisclosureSnapshot = field(
        default_factory=lambda: CapabilityDisclosureSnapshot((), (), ())
    )

    def browser_payload(self) -> dict[str, JsonValue]:
        return {
            "provider": dict(self.provider),
            "technical_profile": self.technical_profile.value,
            "skills": [dict(item) for item in self.skills],
            "capabilities": [dict(item) for item in self.capabilities],
            "context_providers": [dict(item) for item in self.context_providers],
            "evidence_provider_ids": list(self.evidence_provider_ids),
            "configuration_health": [dict(item) for item in self.configuration_health],
            "unavailable_features": [dict(item) for item in self.unavailable_features],
            "disclosure": {
                "available": list(self.disclosure.available),
                "revealed": list(self.disclosure.revealed),
                "active": list(self.disclosure.active),
            },
        }


def technical_access_profile_for_env(env) -> TechnicalAccessProfile:
    """Describe technical reach without granting any new execution authority."""

    user = getattr(env, "user", None)
    if user is not None and user.has_group("base.group_system"):
        return TechnicalAccessProfile.DEVELOPER
    return TechnicalAccessProfile.BUSINESS


def build_effective_assistant_manifest(
    *,
    registry: CapabilityRegistry,
    context: CapabilityContext,
    provider_profile: ProviderProfile,
    skills: SkillCatalog | None = None,
    context_providers: ContextProviderCatalog | None = None,
    evidence_provider_ids: Iterable[str] = (),
    technical_profile: TechnicalAccessProfile = TechnicalAccessProfile.BUSINESS,
    disclosure: CapabilityDisclosureSnapshot | None = None,
    configuration_health: Iterable[Mapping[str, JsonValue]] = (),
) -> EffectiveAssistantManifest:
    """Build a safe projection; it never mutates authority or exposes handlers/instructions.

    Host-only capabilities remain outside the model/user self-description surface. The manifest
    describes the same REASONING/PLAN catalog the model may know, while host validation still uses
    the complete registry independently.
    """

    if not isinstance(technical_profile, TechnicalAccessProfile):
        raise CapabilityError("technical_profile_invalid")
    available_defs = (
        *registry.for_reasoning(context),
        *registry.for_planning(context),
    )
    available_names = tuple(sorted(item.name for item in available_defs))
    disclosure = disclosure or build_disclosure_snapshot(available_names)
    if set(disclosure.available) != set(available_names):
        raise CapabilityError("capability_disclosure_state_invalid")

    context_catalog = context_providers or ContextProviderCatalog()
    context_rows = context_catalog.catalog(context)
    available_context_ids = tuple(
        row["provider_id"]
        for row in context_rows
        if row.get("available") is True and isinstance(row.get("provider_id"), str)
    )
    evidence_ids = tuple(sorted(set(evidence_provider_ids)))
    skill_catalog = skills or SkillCatalog()
    skill_rows = tuple(
        row
        for row in skill_catalog.catalog(
            context,
            capability_names=available_names,
            context_provider_ids=available_context_ids,
            evidence_provider_ids=evidence_ids,
        )
        if row.get("active") is True
    )

    revealed = set(disclosure.revealed)
    by_name = {item.name: item for item in available_defs}
    capability_rows = tuple(
        {
            "name": definition.name,
            "title": definition.title or definition.name,
            "description": definition.description,
            "exposure": definition.exposure.value,
            "effect": definition.effect.value,
            "risk": definition.risk.value,
            "provider_id": registry.provider_for(definition.name),
            "revealed": definition.name in revealed,
        }
        for definition in (by_name[name] for name in available_names)
    )
    provider_health = tuple(
        {
            "provider_id": item.provider_id,
            "state": item.state,
            "error_code": item.error_code or None,
        }
        for item in registry.provider_statuses
    )
    health = provider_health + tuple(dict(item) for item in configuration_health)
    return EffectiveAssistantManifest(
        provider=provider_profile.browser_payload(),
        technical_profile=technical_profile,
        skills=skill_rows,
        capabilities=capability_rows,
        context_providers=context_rows,
        evidence_provider_ids=evidence_ids,
        configuration_health=health,
        unavailable_features=provider_profile.unavailable_features(),
        disclosure=disclosure,
    )


__all__ = [
    "EffectiveAssistantManifest",
    "TechnicalAccessProfile",
    "build_effective_assistant_manifest",
    "technical_access_profile_for_env",
]
