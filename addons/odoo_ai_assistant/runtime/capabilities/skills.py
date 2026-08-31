"""Declarative Skill/Bundle contracts layered above executable capabilities.

Skills organize behavior for the model. They may group instructions and selectors, but
never grant execution authority; every effect still resolves through CapabilityDefinition
and the host-owned executor/policy boundary.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .contracts import CapabilityContext, CapabilityError, JsonValue

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_NAMESPACE_SELECTOR_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\.\*$")
_VERSION_RE = re.compile(r"^[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """One semantic bundle of instructions and extension selectors."""

    skill_id: str
    description: str
    title: str = ""
    version: str = "1"
    instructions: str = ""
    examples: tuple[str, ...] = ()
    capability_selectors: tuple[str, ...] = ()
    context_provider_selectors: tuple[str, ...] = ()
    evidence_provider_selectors: tuple[str, ...] = ()
    default_enabled: bool = True
    activation_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    configuration_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    eval_owner: str = ""

    def __post_init__(self) -> None:
        if not _ID_RE.fullmatch(self.skill_id):
            raise CapabilityError("skill_id_invalid")
        if not _VERSION_RE.fullmatch(self.version):
            raise CapabilityError("skill_version_invalid")
        if not self.description.strip() or len(self.description) > 4_000:
            raise CapabilityError("skill_description_invalid")
        if self.title and len(self.title) > 160:
            raise CapabilityError("skill_title_invalid")
        if len(self.instructions) > 12_000:
            raise CapabilityError("skill_instructions_invalid")
        if len(self.examples) > 16 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 2_000
            for item in self.examples
        ):
            raise CapabilityError("skill_examples_invalid")
        for selectors in (
            self.capability_selectors,
            self.context_provider_selectors,
            self.evidence_provider_selectors,
        ):
            if len(set(selectors)) != len(selectors):
                raise CapabilityError("skill_selector_duplicate")
            if any(not _selector_valid(selector) for selector in selectors):
                raise CapabilityError("skill_selector_invalid")
        if self.eval_owner and len(self.eval_owner) > 160:
            raise CapabilityError("skill_eval_owner_invalid")


class SkillCatalog:
    """Immutable Skill catalog with host-owned effective activation filtering."""

    def __init__(
        self,
        definitions: Iterable[SkillDefinition] = (),
        *,
        skill_providers: Mapping[str, str] | None = None,
    ) -> None:
        by_id: dict[str, SkillDefinition] = {}
        for definition in sorted(definitions, key=lambda item: item.skill_id):
            if definition.skill_id in by_id:
                raise CapabilityError("skill_id_duplicate")
            by_id[definition.skill_id] = definition
        provider_map = dict(skill_providers or {})
        if any(skill_id not in by_id for skill_id in provider_map):
            raise CapabilityError("skill_provider_mapping_invalid")
        self._by_id = by_id
        self._skill_providers = provider_map

    @property
    def definitions(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._by_id.values())

    def resolve(self, skill_id: str) -> SkillDefinition:
        try:
            return self._by_id[skill_id]
        except KeyError:
            raise CapabilityError("skill_not_registered") from None

    def provider_for(self, skill_id: str) -> str | None:
        self.resolve(skill_id)
        return self._skill_providers.get(skill_id)

    def available(
        self,
        context: CapabilityContext,
        *,
        capability_names: Iterable[str],
        context_provider_ids: Iterable[str] = (),
        evidence_provider_ids: Iterable[str] = (),
    ) -> tuple[SkillDefinition, ...]:
        capabilities = frozenset(capability_names)
        context_ids = frozenset(context_provider_ids)
        evidence_ids = frozenset(evidence_provider_ids)
        return tuple(
            definition
            for definition in self.definitions
            if _skill_enabled(definition, context)
            and _selectors_satisfied(definition.capability_selectors, capabilities)
            and _selectors_satisfied(definition.context_provider_selectors, context_ids)
            and _selectors_satisfied(definition.evidence_provider_selectors, evidence_ids)
        )

    def catalog(
        self,
        context: CapabilityContext,
        *,
        capability_names: Iterable[str],
        context_provider_ids: Iterable[str] = (),
        evidence_provider_ids: Iterable[str] = (),
    ) -> tuple[dict[str, JsonValue], ...]:
        active_ids = {
            item.skill_id
            for item in self.available(
                context,
                capability_names=capability_names,
                context_provider_ids=context_provider_ids,
                evidence_provider_ids=evidence_provider_ids,
            )
        }
        capability_set = frozenset(capability_names)
        rows: list[dict[str, JsonValue]] = []
        for definition in self.definitions:
            rows.append(
                {
                    "skill_id": definition.skill_id,
                    "title": definition.title or definition.skill_id,
                    "description": definition.description,
                    "version": definition.version,
                    "active": definition.skill_id in active_ids,
                    "provider_id": self._skill_providers.get(definition.skill_id),
                    "capabilities": [
                        name
                        for name in sorted(capability_set)
                        if any(
                            selector_matches(selector, name)
                            for selector in definition.capability_selectors
                        )
                    ],
                    "context_provider_selectors": list(
                        definition.context_provider_selectors
                    ),
                    "evidence_provider_selectors": list(
                        definition.evidence_provider_selectors
                    ),
                    "eval_owner": definition.eval_owner or None,
                }
            )
        return tuple(rows)

    def instruction_blocks(self, skill_ids: Iterable[str]) -> tuple[str, ...]:
        """Return trusted instructions for already host-selected Skills only."""

        blocks = []
        for skill_id in skill_ids:
            instructions = self.resolve(skill_id).instructions.strip()
            if instructions:
                blocks.append(instructions)
        return tuple(blocks)


def selector_matches(selector: str, identity: str) -> bool:
    if selector.endswith(".*"):
        namespace = selector[:-2]
        return identity.startswith(namespace + ".")
    return identity == selector


def _selector_valid(selector: str) -> bool:
    return bool(_ID_RE.fullmatch(selector) or _NAMESPACE_SELECTOR_RE.fullmatch(selector))


def _selectors_satisfied(selectors: tuple[str, ...], identities: frozenset[str]) -> bool:
    return all(any(selector_matches(selector, item) for item in identities) for selector in selectors)


def _skill_enabled(definition: SkillDefinition, context: CapabilityContext) -> bool:
    overrides = context.metadata.get("skill_enabled", {})
    if not isinstance(overrides, dict):
        overrides = {}
    exact = overrides.get(definition.skill_id)
    if isinstance(exact, bool):
        return exact
    namespace = definition.skill_id.rpartition(".")[0]
    while namespace:
        value = overrides.get(namespace + ".*")
        if isinstance(value, bool):
            return value
        namespace = namespace.rpartition(".")[0]
    return definition.default_enabled


__all__ = ["SkillCatalog", "SkillDefinition", "selector_matches"]
