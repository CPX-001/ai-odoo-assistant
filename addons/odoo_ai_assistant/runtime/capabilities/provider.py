"""Trusted addon extension contract for capability providers.

Phase 7 keeps :class:`CapabilityDefinition` as the atomic executable authority while
allowing installed Odoo addons to contribute definitions and higher-level declarative
resources without editing the core ``runtime.capabilities.providers`` package.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .context import ContextProvider
from .contracts import CapabilityDefinition, CapabilityError, JsonValue
from .skills import SkillDefinition

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PROVIDER_VERSION_RE = re.compile(r"^[1-9][0-9]*$")
_PROVIDER_MARKER_ATTR = "_odoo_ai_capability_provider"

type CapabilityProviderLoader = Callable[[], Iterable[CapabilityDefinition]]


@dataclass(frozen=True, slots=True)
class CapabilityProvider:
    """One trusted installed-code source of Assistant extension resources.

    ``definitions`` is the simple/static executable path. ``loader`` exists for providers
    that need deferred capability construction and is also the failure-isolation boundary.
    A provider may use one or the other, never both. Skills and ContextProviders remain
    declarative/non-authoritative resources layered around those atomic definitions.
    """

    provider_id: str
    version: str = "1"
    definitions: tuple[CapabilityDefinition, ...] = ()
    loader: CapabilityProviderLoader | None = field(default=None, repr=False, compare=False)
    skills: tuple[SkillDefinition, ...] = ()
    context_providers: tuple[ContextProvider, ...] = ()
    title: str = ""
    optional: bool = True
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("capability_provider_id_invalid")
        if not _PROVIDER_VERSION_RE.fullmatch(self.version):
            raise CapabilityError("capability_provider_version_invalid")
        if self.title and len(self.title) > 160:
            raise CapabilityError("capability_provider_title_invalid")
        if self.definitions and self.loader is not None:
            raise CapabilityError("capability_provider_source_ambiguous")
        if any(not isinstance(item, CapabilityDefinition) for item in self.definitions):
            raise CapabilityError("capability_provider_definition_invalid")
        if any(not isinstance(item, SkillDefinition) for item in self.skills):
            raise CapabilityError("capability_provider_skill_invalid")
        if any(not isinstance(item, ContextProvider) for item in self.context_providers):
            raise CapabilityError("capability_provider_context_invalid")
        if len({item.skill_id for item in self.skills}) != len(self.skills):
            raise CapabilityError("skill_id_duplicate")
        if len({item.provider_id for item in self.context_providers}) != len(self.context_providers):
            raise CapabilityError("context_provider_id_duplicate")

    @classmethod
    def from_objects(
        cls,
        *,
        provider_id: str,
        objects: Iterable[object],
        version: str = "1",
        title: str = "",
        optional: bool = True,
        metadata: Mapping[str, JsonValue] | None = None,
        skills: Iterable[SkillDefinition] = (),
        context_providers: Iterable[ContextProvider] = (),
    ) -> CapabilityProvider:
        """Build a static provider from handlers decorated with ``@tool``.

        This is intentionally explicit: installed addon code chooses which objects it
        contributes, while the host still owns identity/conflict validation.
        """

        from .decorators import definition_from_object

        definitions: list[CapabilityDefinition] = []
        for value in objects:
            definition = definition_from_object(value)
            if definition is None:
                raise CapabilityError("capability_provider_definition_invalid")
            definitions.append(definition)
        return cls(
            provider_id=provider_id,
            version=version,
            definitions=tuple(definitions),
            skills=tuple(skills),
            context_providers=tuple(context_providers),
            title=title,
            optional=optional,
            metadata=dict(metadata or {}),
        )

    def load_definitions(self) -> tuple[CapabilityDefinition, ...]:
        values = self.definitions if self.loader is None else tuple(self.loader())
        if any(not isinstance(item, CapabilityDefinition) for item in values):
            raise CapabilityError("capability_provider_definition_invalid")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class CapabilityProviderStatus:
    """Sanitized provider state retained for diagnostics/future manifest projection."""

    provider_id: str
    version: str
    state: str
    optional: bool
    capability_count: int = 0
    error_code: str = ""

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("capability_provider_id_invalid")
        if not _PROVIDER_VERSION_RE.fullmatch(self.version):
            raise CapabilityError("capability_provider_version_invalid")
        if self.state not in {"loaded", "failed"}:
            raise CapabilityError("capability_provider_state_invalid")
        if self.capability_count < 0:
            raise CapabilityError("capability_provider_count_invalid")
        if self.state == "loaded" and self.error_code:
            raise CapabilityError("capability_provider_state_invalid")
        if self.state == "failed" and not self.error_code:
            raise CapabilityError("capability_provider_state_invalid")


def discover_odoo_capability_providers(env) -> tuple[CapabilityProvider, ...]:
    """Discover provider markers from the effective Odoo registry.

    Odoo only materializes models from installed addons in the active registry, so this
    gives third-party addons an Odoo-native extension point without scanning arbitrary
    filesystem/Python packages. Provider markers are trusted code declarations, not DB
    records or model-generated instructions.
    """

    registry = getattr(env, "registry", None)
    models = getattr(registry, "models", None)
    if models is None:
        return ()

    providers: list[CapabilityProvider] = []
    marker_classes: set[type] = set()
    for model_name in sorted(models):
        model_class = models[model_name]
        # Odoo's registry class is synthesized and does not retain custom class
        # attributes in its own namespace.  `_model_classes__` is the ordered set of
        # installed source classes used to construct it; inspect each namespace
        # directly so ordinary Python inheritance still cannot duplicate a marker.
        source_classes = getattr(model_class, "_model_classes__", (model_class,))
        for source_class in source_classes:
            namespace = vars(source_class)
            if _PROVIDER_MARKER_ATTR not in namespace:
                continue
            if source_class in marker_classes:
                continue
            provider = namespace[_PROVIDER_MARKER_ATTR]
            if not isinstance(provider, CapabilityProvider):
                raise CapabilityError("capability_provider_marker_invalid")
            providers.append(provider)
            marker_classes.add(source_class)
    return tuple(providers)


__all__ = [
    "CapabilityProvider",
    "CapabilityProviderLoader",
    "CapabilityProviderStatus",
    "discover_odoo_capability_providers",
]
