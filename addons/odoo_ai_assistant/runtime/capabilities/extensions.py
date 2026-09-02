"""Composition of non-executable Assistant resources from installed providers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .context import (
    ContextContribution,
    ContextProvider,
    ContextProviderCatalog,
    ContextProviderStatus,
)
from .contracts import CapabilityContext, CapabilityError, JsonValue
from .evidence import (
    EvidenceLedger,
    EvidenceProvider,
    EvidenceProviderCatalog,
    EvidenceProviderStatus,
    EvidenceRoutingPolicy,
    EvidenceSearchBatch,
    EvidenceSearchRequest,
)
from .log_evidence import build_odoo_log_evidence_provider
from .provider import CapabilityProvider, discover_odoo_capability_providers
from .registry import CapabilityRegistry, discover_capabilities_for_env
from .runtime_evidence import build_runtime_inventory_evidence_provider
from .skills import SkillCatalog, SkillDefinition, selector_matches
from .source_evidence import build_installed_source_evidence_provider


@dataclass(frozen=True, slots=True)
class AssistantExtensionStatus:
    """Sanitized status for one provider's declarative resource layer."""

    provider_id: str
    state: str
    skill_count: int = 0
    context_provider_count: int = 0
    error_code: str = ""
    evidence_provider_count: int = 0

    def __post_init__(self) -> None:
        if self.state not in {"loaded", "failed"}:
            raise CapabilityError("assistant_extension_state_invalid")
        if (
            self.skill_count < 0
            or self.context_provider_count < 0
            or self.evidence_provider_count < 0
        ):
            raise CapabilityError("assistant_extension_count_invalid")
        if self.state == "loaded" and self.error_code:
            raise CapabilityError("assistant_extension_state_invalid")
        if self.state == "failed" and not self.error_code:
            raise CapabilityError("assistant_extension_state_invalid")


@dataclass(frozen=True, slots=True)
class ActiveAssistantExtensions:
    """Per-turn resources after host availability/activation filtering."""

    skills: tuple[SkillDefinition, ...] = ()
    context: tuple[ContextContribution, ...] = ()
    context_statuses: tuple[ContextProviderStatus, ...] = ()
    evidence_provider_ids: tuple[str, ...] = ()
    evidence_statuses: tuple[EvidenceProviderStatus, ...] = ()

    def host_skill_contract(self) -> tuple[dict[str, JsonValue], ...]:
        return tuple(
            {
                "skill_id": item.skill_id,
                "description": item.description,
                "instructions": item.instructions,
                "examples": list(item.examples),
            }
            for item in self.skills
        )

    def host_evidence_contract(self) -> dict[str, JsonValue]:
        """Host-owned metadata only; retrieved content never enters this partition."""

        return {
            "provider_ids": list(self.evidence_provider_ids),
            "statuses": [
                {
                    "provider_id": item.provider_id,
                    "state": item.state,
                    "kinds": [kind.value for kind in item.kinds],
                    "error_code": item.error_code,
                }
                for item in self.evidence_statuses
            ],
        }

    def untrusted_context_data(self) -> tuple[dict[str, JsonValue], ...]:
        return tuple(
            {"provider_id": item.provider_id, "data": dict(item.data)}
            for item in self.context
        )


@dataclass(frozen=True, slots=True)
class AssistantExtensionCatalog:
    """Effective declarative resources around the executable capability registry."""

    skills: SkillCatalog
    context_providers: ContextProviderCatalog
    statuses: tuple[AssistantExtensionStatus, ...] = ()
    evidence_providers: EvidenceProviderCatalog = field(
        default_factory=EvidenceProviderCatalog
    )

    def activate(
        self,
        context: CapabilityContext,
        *,
        capability_names: Iterable[str],
        evidence_provider_ids: Iterable[str] = (),
    ) -> ActiveAssistantExtensions:
        available_context_ids = tuple(
            item.provider_id for item in self.context_providers.available(context)
        )
        available_evidence, evidence_statuses = self.evidence_providers.availability(context)
        available_evidence_ids = tuple(item.provider_id for item in available_evidence)
        requested_ids = tuple(evidence_provider_ids)
        available_set = set(available_evidence_ids)
        effective_evidence_ids = (
            tuple(item for item in requested_ids if item in available_set)
            if requested_ids
            else available_evidence_ids
        )
        active_skills = self.skills.available(
            context,
            capability_names=capability_names,
            context_provider_ids=available_context_ids,
            evidence_provider_ids=effective_evidence_ids,
        )
        selectors = tuple(
            selector
            for skill in active_skills
            for selector in skill.context_provider_selectors
        )
        selected_context_ids = tuple(
            provider_id
            for provider_id in available_context_ids
            if any(selector_matches(selector, provider_id) for selector in selectors)
        )
        contributions, context_statuses = self.context_providers.collect(
            context,
            provider_ids=selected_context_ids,
        )
        return ActiveAssistantExtensions(
            skills=active_skills,
            context=contributions,
            context_statuses=context_statuses,
            evidence_provider_ids=effective_evidence_ids,
            evidence_statuses=evidence_statuses,
        )

    def search_evidence(
        self,
        context: CapabilityContext,
        request: EvidenceSearchRequest,
        *,
        ledger: EvidenceLedger | None = None,
        routing_policy: EvidenceRoutingPolicy | None = None,
    ) -> EvidenceSearchBatch:
        batch = self.evidence_providers.search(
            context,
            request,
            routing_policy=routing_policy,
        )
        if ledger is not None:
            for ref in batch.refs:
                ledger.register(ref, retain_excerpt=False)
        return batch


def compose_assistant_extensions(
    providers: Iterable[CapabilityProvider],
    *,
    capability_registry: CapabilityRegistry,
    builtin_evidence_providers: Iterable[EvidenceProvider] = (),
) -> AssistantExtensionCatalog:
    """Compose resources only from capability providers accepted by the host."""

    ordered = tuple(sorted(providers, key=lambda item: item.provider_id))
    statuses_by_id = {
        item.provider_id: item for item in capability_registry.provider_statuses
    }
    skills: list[SkillDefinition] = []
    contexts: list[ContextProvider] = []
    evidence: list[EvidenceProvider] = list(builtin_evidence_providers)
    skill_providers: dict[str, str] = {}
    skill_owners: set[str] = set()
    context_owners: set[str] = set()
    evidence_owners: set[str] = {item.provider_id for item in evidence}
    if len(evidence_owners) != len(evidence):
        raise CapabilityError("evidence_provider_id_duplicate")
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
            evidence_owners=evidence_owners,
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
        evidence.extend(provider.evidence_providers)
        for skill in provider.skills:
            skill_owners.add(skill.skill_id)
            skill_providers[skill.skill_id] = provider.provider_id
        context_owners.update(item.provider_id for item in provider.context_providers)
        evidence_owners.update(item.provider_id for item in provider.evidence_providers)
        statuses.append(
            AssistantExtensionStatus(
                provider_id=provider.provider_id,
                state="loaded",
                skill_count=len(provider.skills),
                context_provider_count=len(provider.context_providers),
                evidence_provider_count=len(provider.evidence_providers),
            )
        )

    return AssistantExtensionCatalog(
        skills=SkillCatalog(skills, skill_providers=skill_providers),
        context_providers=ContextProviderCatalog(contexts),
        statuses=tuple(statuses),
        evidence_providers=EvidenceProviderCatalog(evidence),
    )


def discover_assistant_extensions_for_env(
    env,
    *,
    capability_registry: CapabilityRegistry | None = None,
) -> AssistantExtensionCatalog:
    registry = capability_registry or discover_capabilities_for_env(env)
    providers = discover_odoo_capability_providers(env)
    builtin_evidence = (
        build_runtime_inventory_evidence_provider(),
        build_installed_source_evidence_provider(),
        build_odoo_log_evidence_provider(),
    )
    if not providers:
        return AssistantExtensionCatalog(
            skills=SkillCatalog(),
            context_providers=ContextProviderCatalog(),
            evidence_providers=EvidenceProviderCatalog(builtin_evidence),
        )
    return compose_assistant_extensions(
        providers,
        capability_registry=registry,
        builtin_evidence_providers=builtin_evidence,
    )


def _resource_conflict_code(
    provider: CapabilityProvider,
    *,
    skill_owners: set[str],
    context_owners: set[str],
    evidence_owners: set[str] | None = None,
) -> str:
    evidence_owners = evidence_owners or set()
    if any(item.skill_id in skill_owners for item in provider.skills):
        return "skill_id_duplicate"
    if any(item.provider_id in context_owners for item in provider.context_providers):
        return "context_provider_id_duplicate"
    if any(item.provider_id in evidence_owners for item in provider.evidence_providers):
        return "evidence_provider_id_duplicate"
    return ""


__all__ = [
    "ActiveAssistantExtensions",
    "AssistantExtensionCatalog",
    "AssistantExtensionStatus",
    "compose_assistant_extensions",
    "discover_assistant_extensions_for_env",
]
