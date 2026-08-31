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

contracts = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.contracts")
context_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.context")
skills_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.skills")
provider_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.provider")
registry_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.registry")
extensions_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.extensions")

CapabilityDefinition = contracts.CapabilityDefinition
CapabilityEffect = contracts.CapabilityEffect
CapabilityError = contracts.CapabilityError
CapabilityRisk = contracts.CapabilityRisk
ContextProvider = context_module.ContextProvider
SkillDefinition = skills_module.SkillDefinition
CapabilityProvider = provider_module.CapabilityProvider
CapabilityProviderStatus = provider_module.CapabilityProviderStatus
CapabilityRegistry = registry_module.CapabilityRegistry
compose_assistant_extensions = extensions_module.compose_assistant_extensions

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _handler(context, arguments):
    del context, arguments
    return {"ok": True}


def _definition(name: str) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description=f"Read fixture {name}.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        handler=_handler,
    )


def _registry(*providers: CapabilityProvider) -> CapabilityRegistry:
    definitions = tuple(
        definition for provider in providers for definition in provider.definitions
    )
    return CapabilityRegistry(
        definitions,
        provider_statuses=tuple(
            CapabilityProviderStatus(
                provider_id=provider.provider_id,
                version=provider.version,
                state="loaded",
                optional=provider.optional,
                capability_count=len(provider.definitions),
            )
            for provider in providers
        ),
        capability_providers={
            definition.name: provider.provider_id
            for provider in providers
            for definition in provider.definitions
        },
    )


def test_resources_compose_only_after_capability_provider_acceptance() -> None:
    provider = CapabilityProvider(
        provider_id="example.sales",
        definitions=(_definition("example.read_partner"),),
        skills=(
            SkillDefinition(
                skill_id="example.sales_skill",
                description="Sales assistance.",
                capability_selectors=("example.*",),
            ),
        ),
        context_providers=(
            ContextProvider(
                provider_id="example.screen",
                description="Current screen.",
                collect=lambda context: {"turn": context.turn_id},
            ),
        ),
    )

    extensions = compose_assistant_extensions(
        (provider,), capability_registry=_registry(provider)
    )

    assert extensions.skills.resolve("example.sales_skill")
    assert extensions.skills.provider_for("example.sales_skill") == "example.sales"
    assert extensions.context_providers.resolve("example.screen")
    assert extensions.statuses[0].state == "loaded"
    assert extensions.statuses[0].skill_count == 1
    assert extensions.statuses[0].context_provider_count == 1


def test_failed_capability_provider_cannot_contribute_instructions_or_context() -> None:
    provider = CapabilityProvider(
        provider_id="example.failed",
        skills=(SkillDefinition(skill_id="example.failed_skill", description="Never active."),),
        context_providers=(
            ContextProvider(
                provider_id="example.failed_context",
                description="Never active.",
                collect=lambda context: {"turn": context.turn_id},
            ),
        ),
    )
    registry = CapabilityRegistry(
        (),
        provider_statuses=(
            CapabilityProviderStatus(
                provider_id="example.failed",
                version="1",
                state="failed",
                optional=True,
                error_code="capability_provider_load_failed",
            ),
        ),
    )

    extensions = compose_assistant_extensions((provider,), capability_registry=registry)

    assert extensions.skills.definitions == ()
    assert extensions.context_providers.providers == ()
    assert extensions.statuses[0].error_code == "capability_provider_load_failed"


def test_optional_resource_collision_is_fail_isolated_without_shadowing() -> None:
    first = CapabilityProvider(
        provider_id="example.alpha",
        skills=(SkillDefinition(skill_id="example.shared", description="First."),),
    )
    second = CapabilityProvider(
        provider_id="example.beta",
        skills=(SkillDefinition(skill_id="example.shared", description="Second."),),
        optional=True,
    )

    extensions = compose_assistant_extensions(
        (second, first), capability_registry=_registry(first, second)
    )

    assert extensions.skills.provider_for("example.shared") == "example.alpha"
    statuses = {item.provider_id: item for item in extensions.statuses}
    assert statuses["example.alpha"].state == "loaded"
    assert statuses["example.beta"].state == "failed"
    assert statuses["example.beta"].error_code == "skill_id_duplicate"


def test_required_resource_collision_fails_closed() -> None:
    first = CapabilityProvider(
        provider_id="example.alpha",
        context_providers=(
            ContextProvider(
                provider_id="example.shared_context",
                description="First.",
                collect=lambda context: {},
            ),
        ),
    )
    second = CapabilityProvider(
        provider_id="example.beta",
        optional=False,
        context_providers=(
            ContextProvider(
                provider_id="example.shared_context",
                description="Second.",
                collect=lambda context: {},
            ),
        ),
    )

    with pytest.raises(CapabilityError) as captured:
        compose_assistant_extensions(
            (first, second), capability_registry=_registry(first, second)
        )

    assert captured.value.code == "context_provider_id_duplicate"
