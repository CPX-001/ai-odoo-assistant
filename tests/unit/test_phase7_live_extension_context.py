import asyncio
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
        "addons.odoo_ai_assistant.runtime.agent",
        ADDON_ROOT / "runtime/agent",
    ),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules.setdefault(package_name, package)

capabilities = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities")
extension_module = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.agent.extension_context"
)
profile_module = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.agent.provider_profile"
)
codex_context_module = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.agent.codex_extension_context"
)
codex_decision = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.agent.codex_decision"
)

CapabilityConfigResolver = capabilities.CapabilityConfigResolver
CapabilityContext = capabilities.CapabilityContext
CapabilityDefinition = capabilities.CapabilityDefinition
CapabilityEffect = capabilities.CapabilityEffect
CapabilityExposure = capabilities.CapabilityExposure
CapabilityRegistry = capabilities.CapabilityRegistry
CapabilityRisk = capabilities.CapabilityRisk
ContextProvider = capabilities.ContextProvider
ContextProviderCatalog = capabilities.ContextProviderCatalog
DisclosurePolicy = capabilities.DisclosurePolicy
ProviderFeature = capabilities.ProviderFeature
ProviderFeatureState = capabilities.ProviderFeatureState
SkillCatalog = capabilities.SkillCatalog
SkillDefinition = capabilities.SkillDefinition
TechnicalAccessProfile = capabilities.TechnicalAccessProfile
AssistantExtensionCatalog = capabilities.AssistantExtensionCatalog
build_disclosure_snapshot = capabilities.build_disclosure_snapshot
build_effective_assistant_manifest = capabilities.build_effective_assistant_manifest
technical_access_profile_for_env = capabilities.technical_access_profile_for_env
AssistantExtensionDecisionEngine = extension_module.AssistantExtensionDecisionEngine
current_codex_provider_profile = profile_module.current_codex_provider_profile

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _handler(context, arguments):
    del context, arguments
    return {"ok": True}


def _definition(name, *, exposure=CapabilityExposure.REASONING):
    return CapabilityDefinition(
        name=name,
        description=f"Fixture capability {name}.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        exposure=exposure,
        handler=_handler,
    )


class _User:
    def __init__(self, *, developer=False):
        self._developer = developer

    def has_group(self, group):
        return self._developer and group == "base.group_system"


class _Env:
    su = False
    uid = 7

    def __init__(self, *, developer=False):
        self.user = _User(developer=developer)


class _CaptureProvider:
    def __init__(self):
        self.kwargs = None
        self.result = object()

    async def next_decision(self, **kwargs):
        self.kwargs = kwargs
        return self.result


def test_live_extension_wrapper_separates_trusted_skill_from_untrusted_context() -> None:
    read = _definition("example.read")
    plan = _definition("example.plan", exposure=CapabilityExposure.PLAN)
    host = _definition("example.host", exposure=CapabilityExposure.HOST)
    registry = CapabilityRegistry((read, plan, host))
    context_provider = ContextProvider(
        provider_id="example.screen",
        description="Current screen fixture.",
        collect=lambda context: {"record_hint": context.turn_id},
    )
    skill = SkillDefinition(
        skill_id="example.sales",
        description="Example sales behavior.",
        instructions="Prefer the example read when it is relevant.",
        capability_selectors=("example.*",),
        context_provider_selectors=("example.screen",),
    )
    extensions = AssistantExtensionCatalog(
        skills=SkillCatalog((skill,)),
        context_providers=ContextProviderCatalog((context_provider,)),
    )
    provider = _CaptureProvider()
    engine = AssistantExtensionDecisionEngine(
        provider,
        registry=registry,
        extensions=extensions,
        provider_profile=current_codex_provider_profile(),
        config=CapabilityConfigResolver(),
        technical_profile=TechnicalAccessProfile.BUSINESS,
    )
    context = CapabilityContext(env=_Env(), turn_id="turn-7")

    result = asyncio.run(
        engine.next_decision(
            message="describe capabilities",
            conversation_summary="",
            context=context,
            reasoning_capabilities=(read,),
            planning_capabilities=(plan,),
            working_items=({"kind": "user_input", "data": {"message": "x"}},),
            remaining_budgets={},
        )
    )

    assert result is provider.result
    projected = provider.kwargs["working_items"]
    skill_item = next(item for item in projected if item.get("kind") == "host_assistant_extensions")
    manifest_item = next(item for item in projected if item.get("kind") == "host_assistant_manifest")
    context_item = next(item for item in projected if item.get("kind") == "assistant_context")
    assert skill_item["source"] == "host"
    assert skill_item["data"]["skills"][0]["skill_id"] == "example.sales"
    assert manifest_item["data"]["provider"]["provider_id"] == "openai.codex_app_server"
    assert context_item == {
        "kind": "assistant_context",
        "source": "context",
        "provider_id": "example.screen",
        "data": {"record_hint": "turn-7"},
    }


def test_manifest_never_reveals_host_only_capabilities() -> None:
    read = _definition("example.read")
    host = _definition("example.internal", exposure=CapabilityExposure.HOST)
    registry = CapabilityRegistry((read, host))
    context = CapabilityContext(env=_Env(), turn_id="manifest")
    manifest = build_effective_assistant_manifest(
        registry=registry,
        context=context,
        provider_profile=current_codex_provider_profile(),
    ).browser_payload()

    assert [item["name"] for item in manifest["capabilities"]] == ["example.read"]
    assert manifest["disclosure"]["available"] == ["example.read"]


def test_codex_partition_keeps_extension_contract_host_owned_and_jit_context_untrusted() -> None:
    codex_context_module.install_codex_extension_context()
    host, untrusted = codex_decision._partition_provider_context(
        (
            {
                "kind": "host_assistant_extensions",
                "source": "host",
                "data": {"skills": []},
            },
            {
                "kind": "host_assistant_manifest",
                "source": "host",
                "data": {"technical_profile": "business"},
            },
            {
                "kind": "assistant_context",
                "source": "context",
                "provider_id": "example.screen",
                "data": {"label": "untrusted"},
            },
        )
    )

    assert host["assistant_extensions"] == {"skills": []}
    assert host["assistant_manifest"] == {"technical_profile": "business"}
    assert untrusted[0]["kind"] == "assistant_context"

    with pytest.raises(Exception) as captured:
        codex_decision._partition_provider_context(
            (
                {
                    "kind": "host_assistant_manifest",
                    "source": "user",
                    "data": {},
                },
            )
        )
    assert getattr(captured.value, "code", None) == "codex_host_contract_invalid"


def test_current_codex_profile_is_explicit_and_conservative() -> None:
    profile = current_codex_provider_profile()
    assert profile.support(ProviderFeature.STRUCTURED_OUTPUT).state is ProviderFeatureState.NATIVE
    assert profile.support(ProviderFeature.TOOL_CALLING).state is ProviderFeatureState.EMULATED
    assert profile.support(ProviderFeature.ANSWER_STREAMING).state is ProviderFeatureState.NATIVE
    assert profile.support(ProviderFeature.VISION).state is ProviderFeatureState.UNAVAILABLE
    assert profile.support(ProviderFeature.LARGE_CONTEXT).state is ProviderFeatureState.UNAVAILABLE


def test_technical_profile_is_descriptive_only() -> None:
    assert technical_access_profile_for_env(_Env()) is TechnicalAccessProfile.BUSINESS
    assert technical_access_profile_for_env(_Env(developer=True)) is TechnicalAccessProfile.DEVELOPER


def test_progressive_disclosure_scales_to_large_catalog_but_stays_eager_by_default() -> None:
    names = tuple(f"bulk.tool_{index:03d}" for index in range(120))
    eager = build_disclosure_snapshot(names)
    assert eager.available == names
    assert eager.revealed == names

    lazy = build_disclosure_snapshot(
        names,
        policy=DisclosurePolicy(enabled=True, eager_selectors=("bulk.tool_000",)),
        requested_selectors=("bulk.tool_119",),
        active_names=("bulk.tool_050",),
    )
    assert lazy.revealed == (
        "bulk.tool_000",
        "bulk.tool_050",
        "bulk.tool_119",
    )
    assert lazy.active == ("bulk.tool_050",)
