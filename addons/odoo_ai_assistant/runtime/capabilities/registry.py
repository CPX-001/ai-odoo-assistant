"""Deterministic capability discovery, dependency validation, and introspection."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
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

DEFAULT_PROVIDER_PACKAGE = __package__ + ".providers"


class CapabilityRegistry:
    """Immutable catalog and sole source of capability identity/metadata."""

    def __init__(self, definitions=()) -> None:
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
        self._validate_dependencies()

    @property
    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._by_name.values())

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
        if enabled and definition.available_for(context):
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
    definitions: list[CapabilityDefinition] = []
    for module_name in _module_names(package_name):
        definitions.extend(collect_module(importlib.import_module(module_name)))
    return CapabilityRegistry(definitions)


def clear_discovery_cache() -> None:
    discover_capabilities.cache_clear()
