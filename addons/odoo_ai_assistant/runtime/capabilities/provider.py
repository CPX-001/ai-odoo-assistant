"""Trusted addon extension contract for capability providers.

``CapabilityDefinition`` remains the atomic executable authority. Installed Odoo
addons may contribute definitions and declarative resources, but API versioning,
identity and immutable metadata are validated before composition.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .context import ContextProvider
from .contracts import CapabilityDefinition, CapabilityError, JsonValue
from .evidence import EvidenceProvider, freeze_json_mapping
from .skills import SkillDefinition

CAPABILITY_PROVIDER_API_VERSION = "1"
RESERVED_PROVIDER_NAMESPACES = ("odoo.", "assistant.", "host.")

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PROVIDER_VERSION_RE = re.compile(r"^[1-9][0-9]*$")
_PROVIDER_MARKER_ATTR = "_odoo_ai_capability_provider"

type CapabilityProviderLoader = Callable[[], Iterable[CapabilityDefinition]]


def _uses_reserved_namespace(identifier: str) -> bool:
    return identifier.startswith(RESERVED_PROVIDER_NAMESPACES)


@dataclass(frozen=True, slots=True)
class CapabilityProvider:
    """One trusted installed-code source of Assistant extension resources.

    Existing positional field order is preserved. New P8 fields are appended so
    P7 providers remain source-compatible. Reserved ``odoo.*``, ``assistant.*``
    and ``host.*`` identities require ``metadata={"namespace_owner": "core"}``.
    Third-party addons should use a reverse-domain or addon-owned namespace.

    Compatibility and reserved-namespace failures are intentionally *not* raised
    while the marker object is constructed. They are provider-boundary failures and
    are isolated by catalog composition so one incompatible optional addon cannot
    prevent healthy providers or the core catalog from loading.
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
    evidence_providers: tuple[EvidenceProvider, ...] = ()
    api_version: str = CAPABILITY_PROVIDER_API_VERSION

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("capability_provider_id_invalid")
        if not _PROVIDER_VERSION_RE.fullmatch(self.version):
            raise CapabilityError("capability_provider_version_invalid")
        if not isinstance(self.api_version, str) or not _PROVIDER_VERSION_RE.fullmatch(self.api_version):
            raise CapabilityError("capability_provider_api_version_invalid")
        if self.title and len(self.title.encode("utf-8")) > 320:
            raise CapabilityError("capability_provider_title_invalid")
        if self.definitions and self.loader is not None:
            raise CapabilityError("capability_provider_source_ambiguous")

        definitions = tuple(self.definitions)
        skills = tuple(self.skills)
        context_providers = tuple(self.context_providers)
        evidence_providers = tuple(self.evidence_providers)
        metadata = freeze_json_mapping(self.metadata, max_bytes=16 * 1024)

        if any(not isinstance(item, CapabilityDefinition) for item in definitions):
            raise CapabilityError("capability_provider_definition_invalid")
        if any(not isinstance(item, SkillDefinition) for item in skills):
            raise CapabilityError("capability_provider_skill_invalid")
        if any(not isinstance(item, ContextProvider) for item in context_providers):
            raise CapabilityError("capability_provider_context_invalid")
        if any(not isinstance(item, EvidenceProvider) for item in evidence_providers):
            raise CapabilityError("capability_provider_evidence_invalid")
        if len({item.skill_id for item in skills}) != len(skills):
            raise CapabilityError("skill_id_duplicate")
        if len({item.provider_id for item in context_providers}) != len(context_providers):
            raise CapabilityError("context_provider_id_duplicate")
        if len({item.provider_id for item in evidence_providers}) != len(evidence_providers):
            raise CapabilityError("evidence_provider_id_duplicate")

        object.__setattr__(self, "definitions", definitions)
        object.__setattr__(self, "skills", skills)
        object.__setattr__(self, "context_providers", context_providers)
        object.__setattr__(self, "evidence_providers", evidence_providers)
        object.__setattr__(self, "metadata", metadata)

    @property
    def owns_reserved_namespace(self) -> bool:
        return self.metadata.get("namespace_owner") == "core"

    def contract_error_code(
        self,
        definitions: Iterable[CapabilityDefinition] | None = None,
    ) -> str:
        """Return one sanitized host-owned compatibility error, if any."""

        if self.api_version != CAPABILITY_PROVIDER_API_VERSION:
            return "capability_provider_api_version_incompatible"
        if _uses_reserved_namespace(self.provider_id) and not self.owns_reserved_namespace:
            return "capability_provider_namespace_reserved"
        if self.owns_reserved_namespace:
            return ""

        executable = tuple(self.definitions if definitions is None else definitions)
        resource_ids = (
            *(item.name for item in executable),
            *(item.skill_id for item in self.skills),
            *(item.provider_id for item in self.context_providers),
            *(item.provider_id for item in self.evidence_providers),
        )
        if any(_uses_reserved_namespace(identifier) for identifier in resource_ids):
            return "capability_provider_resource_namespace_reserved"
        return ""

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
        evidence_providers: Iterable[EvidenceProvider] = (),
        api_version: str = CAPABILITY_PROVIDER_API_VERSION,
    ) -> CapabilityProvider:
        """Build a static provider from handlers decorated with ``@tool``."""

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
            evidence_providers=tuple(evidence_providers),
            api_version=api_version,
        )

    def load_definitions(self) -> tuple[CapabilityDefinition, ...]:
        try:
            values = self.definitions if self.loader is None else tuple(self.loader())
        except Exception as exc:
            if isinstance(exc, CapabilityError) and exc.args:
                raise CapabilityError(str(exc.args[0])[:160]) from exc
            raise CapabilityError("capability_provider_load_failed") from exc
        if any(not isinstance(item, CapabilityDefinition) for item in values):
            raise CapabilityError("capability_provider_definition_invalid")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class CapabilityProviderStatus:
    """Sanitized provider state retained for diagnostics/manifest projection."""

    provider_id: str
    version: str
    state: str
    optional: bool
    capability_count: int = 0
    error_code: str = ""
    skill_count: int = 0
    context_provider_count: int = 0
    evidence_provider_count: int = 0
    api_version: str = CAPABILITY_PROVIDER_API_VERSION

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("capability_provider_id_invalid")
        if not _PROVIDER_VERSION_RE.fullmatch(self.version):
            raise CapabilityError("capability_provider_version_invalid")
        if not isinstance(self.api_version, str) or not _PROVIDER_VERSION_RE.fullmatch(self.api_version):
            raise CapabilityError("capability_provider_api_version_invalid")
        if self.state not in {"loaded", "failed"}:
            raise CapabilityError("capability_provider_state_invalid")
        counts = (
            self.capability_count,
            self.skill_count,
            self.context_provider_count,
            self.evidence_provider_count,
        )
        if any(item < 0 for item in counts):
            raise CapabilityError("capability_provider_count_invalid")
        if self.state == "loaded" and self.error_code:
            raise CapabilityError("capability_provider_state_invalid")
        if self.state == "failed" and not self.error_code:
            raise CapabilityError("capability_provider_state_invalid")


def discover_odoo_capability_providers(env) -> tuple[CapabilityProvider, ...]:
    """Discover provider markers from the effective Odoo registry.

    Odoo materializes models only from installed addons in the active registry.
    This is an Odoo-native extension point, not an arbitrary package scan.
    """

    registry = getattr(env, "registry", None)
    models = getattr(registry, "models", None)
    if models is None:
        return ()

    providers: list[CapabilityProvider] = []
    marker_classes: set[type] = set()
    for model_name in sorted(models):
        model_class = models[model_name]
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
    "CAPABILITY_PROVIDER_API_VERSION",
    "RESERVED_PROVIDER_NAMESPACES",
    "CapabilityProvider",
    "CapabilityProviderLoader",
    "CapabilityProviderStatus",
    "discover_odoo_capability_providers",
]
