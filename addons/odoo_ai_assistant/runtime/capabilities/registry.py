"""Deterministic capability discovery, dependency validation, and introspection."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Mapping
from functools import lru_cache
from types import ModuleType

from .contracts import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityError,
    CapabilityExposure,
    JsonValue,
)
from .decorators import definition_from_object
from .provider import (
    CapabilityProvider,
    CapabilityProviderStatus,
    discover_odoo_capability_providers,
)

DEFAULT_PROVIDER_PACKAGE = __package__ + ".providers"
CORE_PROVIDER_ID = "odoo_ai_assistant.core"


class CapabilityRegistry:
    """Immutable catalog and sole source of capability identity/metadata."""

    def __init__(
        self,
        definitions=(),
        *,
        provider_statuses: tuple[CapabilityProviderStatus, ...] = (),
        capability_providers: Mapping[str, str] | None = None,
    ) -> None:
        by_name: dict[str, CapabilityDefinition] = {}
        by_executor: dict[str, CapabilityDefinition] = {}
        for definition in sorted(definitions, key=lambda item: item.name):
            if definition.name in by_name:
                raise CapabilityError("capability_name_duplicate")
            if definition.executor_id in by_executor:
                raise CapabilityError("capability_executor_duplicate")
            by_name[definition.name] = definition
            by_executor[definition.executor_id] = definition
        self._by_name = by_name
        self._by_executor = by_executor

        statuses = tuple(sorted(provider_statuses, key=lambda item: item.provider_id))
        if len({item.provider_id for item in statuses}) != len(statuses):
            raise CapabilityError("capability_provider_duplicate")
        provider_map = dict(capability_providers or {})
        if any(name not in by_name for name in provider_map):
            raise CapabilityError("capability_provider_mapping_invalid")
        self._provider_statuses = statuses
        self._capability_providers = provider_map
        self._validate_dependencies()

    @property
    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._by_name.values())

    @property
    def provider_statuses(self) -> tuple[CapabilityProviderStatus, ...]:
        return self._provider_statuses

    def provider_for(self, name: str) -> str | None:
        if name not in self._by_name:
            raise CapabilityError("capability_not_registered")
        return self._capability_providers.get(name)

    def resolve(self, name: str) -> CapabilityDefinition:
        try:
            return self._by_name[name]
        except KeyError:
            raise CapabilityError("capability_not_registered") from None

    def by_namespace(self, namespace: str) -> tuple[CapabilityDefinition, ...]:
        prefix = namespace + "."
        return tuple(
            item
            for item in self.definitions
            if item.namespace == namespace or item.name.startswith(prefix)
        )

    def available(self, context: CapabilityContext) -> tuple[CapabilityDefinition, ...]:
        memo: dict[str, bool] = {}
        return tuple(item for item in self.definitions if self._available(item, context, memo))

    def for_reasoning(self, context: CapabilityContext) -> tuple[CapabilityDefinition, ...]:
        return tuple(
            item
            for item in self.available(context)
            if item.exposure is CapabilityExposure.REASONING
        )

    def for_planning(self, context: CapabilityContext) -> tuple[CapabilityDefinition, ...]:
        return tuple(
            item
            for item in self.available(context)
            if item.exposure is CapabilityExposure.PLAN
        )

    def for_host(self, context: CapabilityContext) -> tuple[CapabilityDefinition, ...]:
        return tuple(
            item
            for item in self.available(context)
            if item.exposure is CapabilityExposure.HOST
        )

    def model_catalog(self, context: CapabilityContext) -> tuple[dict[str, JsonValue], ...]:
        """Descriptors the model may know: reasoning-callable plus plan-only operations."""
        visible = (*self.for_reasoning(context), *self.for_planning(context))
        return tuple(item.wire_descriptor() for item in visible)

    def wire_catalog(self, context: CapabilityContext) -> tuple[dict[str, JsonValue], ...]:
        """Backward-compatible alias: only directly callable reasoning capabilities."""
        return tuple(item.wire_descriptor() for item in self.for_reasoning(context))

    def catalog(
        self,
        context: CapabilityContext | None = None,
    ) -> tuple[dict[str, JsonValue], ...]:
        available_names = None
        if context is not None:
            available_names = {item.name for item in self.available(context)}
        rows: list[dict[str, JsonValue]] = []
        for item in self.definitions:
            rows.append(
                {
                    "name": item.name,
                    "namespace": item.namespace,
                    "title": item.title or item.name,
                    "version": item.version,
                    "exposure": item.exposure.value,
                    "effect": item.effect.value,
                    "risk": item.risk.value,
                    "approval": item.approval.value,
                    "default_enabled": item.default_enabled,
                    "available": (
                        item.name in available_names
                        if available_names is not None
                        else None
                    ),
                    "dependencies": [dep.name for dep in item.dependencies],
                    "settings": [setting.key for setting in item.settings],
                    "provider": item.source_module,
                    "provider_id": self._capability_providers.get(item.name),
                    "handler": item.source_qualname,
                }
            )
        return tuple(rows)

    def _available(
        self,
        definition: CapabilityDefinition,
        context: CapabilityContext,
        memo: dict[str, bool],
    ) -> bool:
        if definition.name in memo:
            return memo[definition.name]
        enabled = _enabled_by_context(definition, context)
        if enabled:
            enabled = definition.available_for(context)
        if enabled:
            enabled = all(
                self._available(self.resolve(dep.name), context, memo)
                for dep in definition.dependencies
            )
        memo[definition.name] = enabled
        return enabled

    def _validate_dependencies(self) -> None:
        for definition in self.definitions:
            for dependency in definition.dependencies:
                target = self._by_name.get(dependency.name)
                if target is None:
                    raise CapabilityError("capability_dependency_missing")
                if int(target.version) < int(dependency.minimum_version):
                    raise CapabilityError("capability_dependency_version_mismatch")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise CapabilityError("capability_dependency_cycle")
            if name in visited:
                return
            visiting.add(name)
            for dependency in self._by_name[name].dependencies:
                visit(dependency.name)
            visiting.remove(name)
            visited.add(name)

        for name in self._by_name:
            visit(name)


def _enabled_by_context(
    definition: CapabilityDefinition,
    context: CapabilityContext,
) -> bool:
    overrides = context.metadata.get("capability_enabled", {})
    if not isinstance(overrides, dict):
        overrides = {}
    exact = overrides.get(definition.name)
    if isinstance(exact, bool):
        return exact
    namespace = definition.namespace
    while namespace:
        value = overrides.get(namespace + ".*")
        if isinstance(value, bool):
            return value
        namespace = namespace.rpartition(".")[0]
    return definition.default_enabled


def collect_module(module: ModuleType) -> tuple[CapabilityDefinition, ...]:
    definitions: list[CapabilityDefinition] = []
    for _, value in inspect.getmembers(module):
        definition = definition_from_object(value)
        if definition is None or definition.source_module != module.__name__:
            continue
        definitions.append(definition)
    return tuple(sorted(definitions, key=lambda item: item.name))


def _module_names(package_name: str) -> tuple[str, ...]:
    package = importlib.import_module(package_name)
    names = [package.__name__]
    package_path = getattr(package, "__path__", None)
    if package_path is not None:
        names.extend(
            item.name
            for item in pkgutil.walk_packages(package_path, package.__name__ + ".")
            if not item.name.rsplit(".", 1)[-1].startswith("_")
        )
    return tuple(sorted(set(names)))


@lru_cache(maxsize=8)
def discover_capabilities(
    package_name: str = DEFAULT_PROVIDER_PACKAGE,
) -> CapabilityRegistry:
    """Discover the built-in package catalog.

    External installed-addon providers are composed by ``discover_capabilities_for_env``;
    keeping this package scan cached preserves the dependency-light/core discovery path.
    """

    definitions: list[CapabilityDefinition] = []
    for module_name in _module_names(package_name):
        definitions.extend(collect_module(importlib.import_module(module_name)))
    status = CapabilityProviderStatus(
        provider_id=CORE_PROVIDER_ID,
        version="1",
        state="loaded",
        optional=False,
        capability_count=len(definitions),
    )
    return CapabilityRegistry(
        definitions,
        provider_statuses=(status,),
        capability_providers={item.name: CORE_PROVIDER_ID for item in definitions},
    )


def compose_capability_registry(
    base_registry: CapabilityRegistry,
    providers: tuple[CapabilityProvider, ...] | list[CapabilityProvider],
) -> CapabilityRegistry:
    """Compose trusted extension providers over one already-valid base catalog.

    Provider identity conflicts fail closed. Optional provider loader/definition/conflict
    failures are isolated and retained as sanitized status instead of removing core tools.
    Required providers fail the composition.
    """

    ordered = tuple(sorted(providers, key=lambda item: item.provider_id))
    provider_ids = [item.provider_id for item in ordered]
    if len(set(provider_ids)) != len(provider_ids):
        raise CapabilityError("capability_provider_duplicate")
    base_provider_ids = {item.provider_id for item in base_registry.provider_statuses}
    if any(provider_id in base_provider_ids for provider_id in provider_ids):
        raise CapabilityError("capability_provider_duplicate")

    statuses = list(base_registry.provider_statuses)
    loaded: dict[str, tuple[CapabilityDefinition, ...]] = {}
    provider_by_id = {item.provider_id: item for item in ordered}

    for provider in ordered:
        try:
            definitions = provider.load_definitions()
            _validate_provider_local_definitions(definitions)
        except Exception as error:  # trusted extension boundary; never expose raw provider errors
            if not provider.optional:
                raise CapabilityError("capability_provider_load_failed") from error
            statuses.append(
                CapabilityProviderStatus(
                    provider_id=provider.provider_id,
                    version=provider.version,
                    state="failed",
                    optional=True,
                    error_code="capability_provider_load_failed",
                )
            )
            continue
        loaded[provider.provider_id] = definitions

    conflicts = _provider_conflicts(base_registry.definitions, loaded)
    for provider_id, error_code in sorted(conflicts.items()):
        provider = provider_by_id[provider_id]
        if not provider.optional:
            raise CapabilityError(error_code)
        loaded.pop(provider_id, None)
        statuses.append(
            CapabilityProviderStatus(
                provider_id=provider.provider_id,
                version=provider.version,
                state="failed",
                optional=True,
                error_code=error_code,
            )
        )

    definitions = list(base_registry.definitions)
    capability_providers = {
        item.name: base_registry.provider_for(item.name)
        for item in base_registry.definitions
        if base_registry.provider_for(item.name) is not None
    }
    for provider in ordered:
        provider_definitions = loaded.get(provider.provider_id)
        if provider_definitions is None:
            continue
        definitions.extend(provider_definitions)
        capability_providers.update(
            {item.name: provider.provider_id for item in provider_definitions}
        )
        statuses.append(
            CapabilityProviderStatus(
                provider_id=provider.provider_id,
                version=provider.version,
                state="loaded",
                optional=provider.optional,
                capability_count=len(provider_definitions),
            )
        )

    try:
        return CapabilityRegistry(
            definitions,
            provider_statuses=tuple(statuses),
            capability_providers=capability_providers,
        )
    except CapabilityError as error:
        # Dependency/cycle failures are provider contract failures too. If every
        # extension is optional, preserve the valid core catalog rather than let one
        # third-party declaration take the Assistant down. Detailed attribution is a
        # later diagnostics concern; the current status remains safely sanitized.
        if loaded and all(provider_by_id[item].optional for item in loaded):
            failed_statuses = [
                item
                for item in statuses
                if item.provider_id not in loaded
            ]
            failed_statuses.extend(
                CapabilityProviderStatus(
                    provider_id=provider_id,
                    version=provider_by_id[provider_id].version,
                    state="failed",
                    optional=True,
                    error_code=error.code,
                )
                for provider_id in sorted(loaded)
            )
            return CapabilityRegistry(
                base_registry.definitions,
                provider_statuses=tuple(failed_statuses),
                capability_providers={
                    item.name: base_registry.provider_for(item.name)
                    for item in base_registry.definitions
                    if base_registry.provider_for(item.name) is not None
                },
            )
        raise


def discover_capabilities_for_env(
    env,
    package_name: str = DEFAULT_PROVIDER_PACKAGE,
) -> CapabilityRegistry:
    """Return the effective catalog for one active Odoo registry/environment."""

    base_registry = discover_capabilities(package_name)
    providers = discover_odoo_capability_providers(env)
    if not providers:
        return base_registry
    return compose_capability_registry(base_registry, providers)


def _validate_provider_local_definitions(
    definitions: tuple[CapabilityDefinition, ...],
) -> None:
    names: set[str] = set()
    executors: set[str] = set()
    for definition in definitions:
        if definition.name in names:
            raise CapabilityError("capability_name_duplicate")
        if definition.executor_id in executors:
            raise CapabilityError("capability_executor_duplicate")
        names.add(definition.name)
        executors.add(definition.executor_id)


def _provider_conflicts(
    base_definitions: tuple[CapabilityDefinition, ...],
    loaded: Mapping[str, tuple[CapabilityDefinition, ...]],
) -> dict[str, str]:
    conflicts: dict[str, str] = {}
    name_owners: dict[str, set[str]] = {}
    executor_owners: dict[str, set[str]] = {}

    for definition in base_definitions:
        name_owners.setdefault(definition.name, set()).add("__core__")
        executor_owners.setdefault(definition.executor_id, set()).add("__core__")
    for provider_id, definitions in loaded.items():
        for definition in definitions:
            name_owners.setdefault(definition.name, set()).add(provider_id)
            executor_owners.setdefault(definition.executor_id, set()).add(provider_id)

    for owners in name_owners.values():
        if len(owners) <= 1:
            continue
        for provider_id in owners - {"__core__"}:
            conflicts.setdefault(provider_id, "capability_name_duplicate")
    for owners in executor_owners.values():
        if len(owners) <= 1:
            continue
        for provider_id in owners - {"__core__"}:
            conflicts.setdefault(provider_id, "capability_executor_duplicate")
    return conflicts


def clear_discovery_cache() -> None:
    discover_capabilities.cache_clear()
