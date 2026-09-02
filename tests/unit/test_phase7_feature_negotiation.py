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
features_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.features")
disclosure_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.disclosure")
provider_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.provider")
registry_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.registry")
manifest_module = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.manifest")

CapabilityContext = contracts.CapabilityContext
CapabilityDefinition = contracts.CapabilityDefinition
CapabilityEffect = contracts.CapabilityEffect
CapabilityError = contracts.CapabilityError
CapabilityRisk = contracts.CapabilityRisk
ContextProvider = context_module.ContextProvider
ContextProviderCatalog = context_module.ContextProviderCatalog
SkillDefinition = skills_module.SkillDefinition
SkillCatalog = skills_module.SkillCatalog
ProviderFeature = features_module.ProviderFeature
ProviderFeatureState = features_module.ProviderFeatureState
ProviderFeatureSupport = features_module.ProviderFeatureSupport
ProviderProfile = features_module.ProviderProfile
DisclosurePolicy = disclosure_module.DisclosurePolicy
build_disclosure_snapshot = disclosure_module.build_disclosure_snapshot
CapabilityProvider = provider_module.CapabilityProvider
CapabilityRegistry = registry_module.CapabilityRegistry
build_effective_assistant_manifest = manifest_module.build_effective_assistant_manifest
TechnicalAccessProfile = manifest_module.TechnicalAccessProfile

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


def _profile() -> ProviderProfile:
    return ProviderProfile(
        provider_id="openai.codex",
        features=tuple(
            ProviderFeatureSupport(
                feature=feature,
                state=(
                    ProviderFeatureState.UNAVAILABLE
                    if feature is ProviderFeature.VISION
                    else ProviderFeatureState.NATIVE
                ),
                reason_code="provider_feature_not_configured"
                if feature is ProviderFeature.VISION
                else "",
            )
            for feature in ProviderFeature
        ),
        context_window_tokens=200_000,
        max_output_tokens=32_000,
    )


def test_skill_catalog_resolves_selectors_without_granting_authority() -> None:
    skill = SkillDefinition(
        skill_id="example.sales",
        description="Sales assistance.",
        instructions="Use sales capabilities only when relevant.",
        capability_selectors=("example.*",),
    )
    catalog = SkillCatalog((skill,))
    context = CapabilityContext(env=object(), turn_id="turn")

    active = catalog.available(
        context,
        capability_names=("core.identity", "example.read_partner"),
    )
    assert active == (skill,)
    assert catalog.catalog(
        context,
        capability_names=("core.identity", "example.read_partner"),
    )[0]["capabilities"] == ["example.read_partner"]

    disabled = CapabilityContext(
        env=object(),
        turn_id="turn",
        metadata={"skill_enabled": {"example.sales": False}},
    )
    assert not catalog.available(
        disabled,
        capability_names=("example.read_partner",),
    )


def test_context_provider_is_bounded_and_optional_failure_is_sanitized() -> None:
    good = ContextProvider(
        provider_id="example.screen",
        description="Current screen context.",
        collect=lambda context: {"turn": context.turn_id},
    )

    def broken(context):
        del context
        raise RuntimeError("secret raw detail")

    bad = ContextProvider(
        provider_id="example.broken",
        description="Broken optional provider.",
        collect=broken,
        optional=True,
    )
    catalog = ContextProviderCatalog((good, bad))
    contributions, statuses = catalog.collect(
        CapabilityContext(env=object(), turn_id="abc")
    )

    assert contributions[0].provider_id == "example.screen"
    assert contributions[0].data == {"turn": "abc"}
    state = {item.provider_id: item for item in statuses}
    assert state["example.broken"].state == "failed"
    assert state["example.broken"].error_code == "context_provider_load_failed"


def test_provider_profile_requires_complete_explicit_feature_matrix() -> None:
    profile = _profile()
    assert profile.support(ProviderFeature.TOOL_CALLING).state is ProviderFeatureState.NATIVE
    assert profile.unavailable_features() == (
        {"feature": "vision", "reason_code": "provider_feature_not_configured"},
    )

    with pytest.raises(CapabilityError) as captured:
        ProviderProfile(
            provider_id="openai.codex",
            features=(
                ProviderFeatureSupport(
                    feature=ProviderFeature.TOOL_CALLING,
                    state=ProviderFeatureState.NATIVE,
                ),
            ),
        )
    assert captured.value.code == "provider_feature_matrix_incomplete"


def test_capability_provider_can_carry_non_authoritative_skill_and_context_resources() -> None:
    skill = SkillDefinition(skill_id="example.sales", description="Sales assistance.")
    context_provider = ContextProvider(
        provider_id="example.screen",
        description="Current screen.",
        collect=lambda context: {"turn": context.turn_id},
    )
    definition = _definition("example.read_partner")
    provider = CapabilityProvider(
        provider_id="example.extension",
        definitions=(definition,),
        skills=(skill,),
        context_providers=(context_provider,),
    )

    assert provider.load_definitions() == (definition,)
    assert provider.skills == (skill,)
    assert provider.context_providers == (context_provider,)


def test_disclosure_is_eager_by_default_and_lazy_only_when_enabled() -> None:
    available = ("odoo.query_records", "sales.confirm_order", "sales.read_order")
    eager = build_disclosure_snapshot(available)
    assert eager.revealed == tuple(sorted(available))

    lazy = build_disclosure_snapshot(
        available,
        policy=DisclosurePolicy(enabled=True, eager_selectors=("odoo.*",)),
        requested_selectors=("sales.read_order",),
        active_names=("sales.confirm_order",),
    )
    assert lazy.revealed == (
        "odoo.query_records",
        "sales.confirm_order",
        "sales.read_order",
    )
    assert lazy.active == ("sales.confirm_order",)


def test_manifest_is_derived_projection_not_a_second_authority_registry() -> None:
    definition = _definition("example.read_partner")
    registry = CapabilityRegistry((definition,))
    context = CapabilityContext(env=object(), turn_id="manifest")
    skills = SkillCatalog(
        (
            SkillDefinition(
                skill_id="example.sales",
                description="Sales assistance.",
                instructions="Private trusted behavior instructions.",
                capability_selectors=("example.*",),
            ),
        )
    )
    contexts = ContextProviderCatalog(
        (
            ContextProvider(
                provider_id="example.screen",
                description="Current screen.",
                collect=lambda current: {"turn": current.turn_id},
            ),
        )
    )

    manifest = build_effective_assistant_manifest(
        registry=registry,
        context=context,
        provider_profile=_profile(),
        skills=skills,
        context_providers=contexts,
        technical_profile=TechnicalAccessProfile.BUSINESS,
    ).browser_payload()

    assert manifest["technical_profile"] == "user"
    assert manifest["capabilities"][0]["name"] == "example.read_partner"
    assert manifest["skills"][0]["skill_id"] == "example.sales"
    assert "instructions" not in manifest["skills"][0]
    assert manifest["unavailable_features"][0]["feature"] == "vision"
