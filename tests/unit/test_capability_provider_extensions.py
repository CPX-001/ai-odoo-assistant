import importlib
import sys
import types
from pathlib import Path

import pytest

ADDON_ROOT = Path(__file__).resolve().parents[2] / "addons/odoo_ai_assistant"
for package_name, package_path in (
    ("addons.odoo_ai_assistant", ADDON_ROOT),
    ("addons.odoo_ai_assistant.runtime", ADDON_ROOT / "runtime"),
    (
        "addons.odoo_ai_assistant.runtime.capabilities",
        ADDON_ROOT / "runtime/capabilities",
    ),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules.setdefault(package_name, package)

contracts = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.contracts"
)
decorators = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.decorators"
)
provider_module = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.provider"
)
registry_module = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.registry"
)

CapabilityDefinition = contracts.CapabilityDefinition
CapabilityContext = contracts.CapabilityContext
CapabilityDependency = contracts.CapabilityDependency
CapabilityEffect = contracts.CapabilityEffect
CapabilityError = contracts.CapabilityError
CapabilityRisk = contracts.CapabilityRisk
CapabilityProvider = provider_module.CapabilityProvider
CapabilityProviderStatus = provider_module.CapabilityProviderStatus
CapabilityRegistry = registry_module.CapabilityRegistry
compose_capability_registry = registry_module.compose_capability_registry
discover_odoo_capability_providers = provider_module.discover_odoo_capability_providers
tool = decorators.tool

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _handler(context, arguments):
    del context, arguments
    return {"ok": True}


def _definition(name: str, *, dependencies=(), guard=None) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description=f"Read-only test capability {name}.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        handler=_handler,
        dependencies=dependencies,
        guard=guard,
    )


def _base_registry() -> CapabilityRegistry:
    definition = _definition("core.identity")
    return CapabilityRegistry(
        (definition,),
        provider_statuses=(
            CapabilityProviderStatus(
                provider_id="odoo_ai_assistant.core",
                version="1",
                state="loaded",
                optional=False,
                capability_count=1,
            ),
        ),
        capability_providers={definition.name: "odoo_ai_assistant.core"},
    )


def test_static_provider_composes_without_editing_core_catalog() -> None:
    external = _definition("example.read_partner")
    provider = CapabilityProvider(
        provider_id="example.sales",
        version="2",
        definitions=(external,),
    )

    registry = compose_capability_registry(_base_registry(), (provider,))

    assert registry.resolve(external.name) is external
    assert registry.provider_for(external.name) == "example.sales"
    assert registry.catalog()[1]["provider_id"] == "example.sales"
    status = {item.provider_id: item for item in registry.provider_statuses}["example.sales"]
    assert status.state == "loaded"
    assert status.version == "2"
    assert status.api_version == provider_module.CAPABILITY_PROVIDER_API_VERSION
    assert status.capability_count == 1


def test_provider_from_objects_accepts_explicit_decorated_handlers() -> None:
    @tool(
        name="example.decorated_read",
        description="Read one explicit fixture.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
    )
    def decorated(context, arguments):
        del context, arguments
        return {"ok": True}

    provider = CapabilityProvider.from_objects(
        provider_id="example.decorated",
        objects=(decorated,),
    )

    registry = compose_capability_registry(_base_registry(), (provider,))
    assert registry.resolve("example.decorated_read").source_qualname.endswith("decorated")


def test_duplicate_provider_identity_is_rejected_before_loading() -> None:
    providers = (
        CapabilityProvider(provider_id="example.duplicate", definitions=()),
        CapabilityProvider(provider_id="example.duplicate", definitions=()),
    )

    with pytest.raises(CapabilityError) as captured:
        compose_capability_registry(_base_registry(), providers)

    assert captured.value.code == "capability_provider_duplicate"


def test_optional_provider_loader_failure_isolated_from_core() -> None:
    def broken_loader():
        raise RuntimeError("private failure detail must not escape")

    registry = compose_capability_registry(
        _base_registry(),
        (
            CapabilityProvider(
                provider_id="example.optional_broken",
                loader=broken_loader,
                optional=True,
            ),
        ),
    )

    assert registry.resolve("core.identity")
    status = {item.provider_id: item for item in registry.provider_statuses}[
        "example.optional_broken"
    ]
    assert status.state == "failed"
    assert status.error_code == "capability_provider_load_failed"


def test_required_provider_loader_failure_blocks_composition() -> None:
    def broken_loader():
        raise RuntimeError("boom")

    with pytest.raises(CapabilityError) as captured:
        compose_capability_registry(
            _base_registry(),
            (
                CapabilityProvider(
                    provider_id="example.required_broken",
                    loader=broken_loader,
                    optional=False,
                ),
            ),
        )

    assert captured.value.code == "capability_provider_load_failed"


def test_optional_provider_capability_collision_is_rejected_not_shadowed() -> None:
    conflicting = _definition("core.identity")
    registry = compose_capability_registry(
        _base_registry(),
        (
            CapabilityProvider(
                provider_id="example.conflicting",
                definitions=(conflicting,),
            ),
        ),
    )

    assert registry.provider_for("core.identity") == "odoo_ai_assistant.core"
    status = {item.provider_id: item for item in registry.provider_statuses}[
        "example.conflicting"
    ]
    assert status.state == "failed"
    assert status.error_code == "capability_name_duplicate"


def test_optional_dependency_failure_preserves_healthy_sibling_provider() -> None:
    dependent = _definition(
        "example.needs_missing",
        dependencies=(CapabilityDependency("missing.capability"),),
    )
    healthy = _definition("healthy.read")
    registry = compose_capability_registry(
        _base_registry(),
        (
            CapabilityProvider(
                provider_id="example.bad_dependency",
                definitions=(dependent,),
            ),
            CapabilityProvider(
                provider_id="healthy.provider",
                definitions=(healthy,),
            ),
        ),
    )

    assert [item.name for item in registry.definitions] == [
        "core.identity",
        "healthy.read",
    ]
    status = {item.provider_id: item for item in registry.provider_statuses}
    assert status["example.bad_dependency"].state == "failed"
    assert status["example.bad_dependency"].error_code == "capability_dependency_missing"
    assert status["healthy.provider"].state == "loaded"


def test_cycle_isolated_to_involved_optional_providers_only() -> None:
    alpha = _definition(
        "cycle.alpha",
        dependencies=(CapabilityDependency("cycle.beta"),),
    )
    beta = _definition(
        "cycle.beta",
        dependencies=(CapabilityDependency("cycle.alpha"),),
    )
    healthy = _definition("healthy.read")

    registry = compose_capability_registry(
        _base_registry(),
        (
            CapabilityProvider(provider_id="cycle.provider_alpha", definitions=(alpha,)),
            CapabilityProvider(provider_id="cycle.provider_beta", definitions=(beta,)),
            CapabilityProvider(provider_id="healthy.provider", definitions=(healthy,)),
        ),
    )

    assert [item.name for item in registry.definitions] == [
        "core.identity",
        "healthy.read",
    ]
    status = {item.provider_id: item for item in registry.provider_statuses}
    assert status["cycle.provider_alpha"].error_code == "capability_dependency_cycle"
    assert status["cycle.provider_beta"].error_code == "capability_dependency_cycle"
    assert status["healthy.provider"].state == "loaded"


def test_capability_guard_exception_fails_closed_without_escaping_details() -> None:
    def exploding_guard(_context):
        raise RuntimeError("private guard detail")

    definition = _definition("example.guarded", guard=exploding_guard)
    context = CapabilityContext(
        env=types.SimpleNamespace(user=types.SimpleNamespace(has_group=lambda _group: True)),
        turn_id="guard",
    )

    assert CapabilityRegistry((definition,)).available(context) == ()


def test_odoo_registry_marker_discovery_is_deterministic_and_direct_only() -> None:
    first = CapabilityProvider(provider_id="example.alpha")
    second = CapabilityProvider(provider_id="example.beta")

    class Alpha:
        _odoo_ai_capability_provider = first

    class Beta:
        _odoo_ai_capability_provider = second

    class Inherited(Alpha):
        pass

    registry = types.SimpleNamespace(
        models={
            "z.beta": Beta,
            "a.alpha": Alpha,
            "m.inherited": Inherited,
        }
    )
    env = types.SimpleNamespace(registry=registry)

    assert discover_odoo_capability_providers(env) == (first, second)


def test_odoo_registry_marker_discovery_inspects_synthesized_model_sources() -> None:
    provider = CapabilityProvider(provider_id="example.installed")

    class InstalledSource:
        _odoo_ai_capability_provider = provider

    class SynthesizedModel:
        _model_classes__ = (InstalledSource, object)

    registry = types.SimpleNamespace(models={"example.installed": SynthesizedModel})
    env = types.SimpleNamespace(registry=registry)

    assert discover_odoo_capability_providers(env) == (provider,)


def test_registry_excludes_capability_when_required_group_is_missing() -> None:
    definition = CapabilityDefinition(
        name="example.admin_probe",
        description="Read-only capability restricted to administrators.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        handler=_handler,
        required_groups=("base.group_system",),
    )
    user = types.SimpleNamespace(has_group=lambda group: False)
    env = types.SimpleNamespace(user=user)
    context = CapabilityContext(env=env, turn_id="limited-user")

    assert CapabilityRegistry((definition,)).available(context) == ()
