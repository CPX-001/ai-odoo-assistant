"""Deterministic capability discovery and immutable catalog construction."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from functools import lru_cache
from types import ModuleType

from .contracts import CapabilityContext, CapabilityDefinition, CapabilityError
from .decorators import definition_from_object

DEFAULT_PROVIDER_PACKAGE = __package__ + ".providers"


class CapabilityRegistry:
    """Immutable-by-convention catalog built from discovered provider modules."""

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

    @property
    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._by_name.values())

    def resolve(self, name: str) -> CapabilityDefinition:
        try:
            return self._by_name[name]
        except KeyError:
            raise CapabilityError("capability_not_registered") from None

    def available(self, context: CapabilityContext) -> tuple[CapabilityDefinition, ...]:
        return tuple(item for item in self.definitions if item.available_for(context))

    def wire_catalog(self, context: CapabilityContext) -> tuple[dict[str, object], ...]:
        return tuple(item.wire_descriptor() for item in self.available(context))


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
    """Import provider modules and discover decorated handlers automatically."""

    definitions: list[CapabilityDefinition] = []
    for module_name in _module_names(package_name):
        definitions.extend(collect_module(importlib.import_module(module_name)))
    return CapabilityRegistry(definitions)


def clear_discovery_cache() -> None:
    """Test/development hook; production discovery is cached per Odoo worker."""

    discover_capabilities.cache_clear()
