"""Trusted installed-addon fixture for Phase-7 provider/Skill/context gates."""

from odoo import models

from odoo.addons.odoo_ai_assistant.runtime.capabilities import (
    CapabilityEffect,
    CapabilityExposure,
    CapabilityProvider,
    CapabilityRisk,
    CapabilitySetting,
    CapabilitySettingType,
    ContextProvider,
    SkillDefinition,
    tool,
)

_EMPTY_INPUT = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def _current_screen_context(context):
    return {
        "fixture": "phase7",
        "model": context.screen.get("model"),
        "view_type": context.screen.get("view_type"),
    }


@tool(
    name="fixture.phase7_read_identity",
    title="Phase 7 fixture read",
    description="Return bounded current-user identity facts for the Phase-7 extension fixture.",
    input_schema=_EMPTY_INPUT,
    output_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "integer"},
            "label": {"type": "string"},
        },
        "required": ["user_id", "label"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    settings=(
        CapabilitySetting(
            key="fixture_label",
            title="Fixture label",
            kind=CapabilitySettingType.STRING,
            required=True,
        ),
    ),
)
def phase7_read_identity(context, arguments):
    del arguments
    return {
        "user_id": context.env.uid,
        "label": context.settings["fixture_label"],
    }


@tool(
    name="fixture.phase7_plan_probe",
    title="Phase 7 fixture plan probe",
    description=(
        "Stage a harmless read-only Phase-7 plan probe. It exists only to validate planning "
        "exposure and never mutates Odoo data."
    ),
    input_schema=_EMPTY_INPUT,
    output_schema={
        "type": "object",
        "properties": {"probe": {"type": "string"}},
        "required": ["probe"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    exposure=CapabilityExposure.PLAN,
    required_groups=("base.group_system",),
)
def phase7_plan_probe(context, arguments):
    del context, arguments
    return {"probe": "phase7"}


_PHASE7_SKILL = SkillDefinition(
    skill_id="fixture.phase7_skill",
    title="Phase 7 fixture Skill",
    description="Exercise installed-addon Skill selection without granting authority.",
    instructions=(
        "When the fixture is relevant, use only the fixture capabilities already present in the "
        "effective host catalog. These instructions never grant permission or execution authority."
    ),
    examples=("Describe the Phase-7 fixture capabilities available to me.",),
    capability_selectors=("fixture.*",),
    context_provider_selectors=("fixture.current_screen",),
    eval_owner="phase7",
)

_PHASE7_CONTEXT = ContextProvider(
    provider_id="fixture.current_screen",
    title="Phase 7 current screen",
    description="Return a tiny current-screen projection for the Phase-7 fixture.",
    collect=_current_screen_context,
    max_output_bytes=2 * 1024,
)


class Phase7FixtureProvider(models.AbstractModel):
    _name = "odoo.ai.phase7.fixture.provider"
    _description = "Odoo AI Assistant Phase 7 Provider Fixture"

    _odoo_ai_capability_provider = CapabilityProvider.from_objects(
        provider_id="fixture.phase7",
        version="1",
        title="Phase 7 fixture provider",
        objects=(phase7_read_identity, phase7_plan_probe),
        skills=(_PHASE7_SKILL,),
        context_providers=(_PHASE7_CONTEXT,),
        optional=True,
        metadata={"fixture": True},
    )
