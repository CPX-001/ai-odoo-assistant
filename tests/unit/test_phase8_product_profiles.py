from __future__ import annotations

import importlib
import sys
import types
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

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

manifest = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.manifest")
profiles = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.profiles")

EffectiveAssistantManifest = manifest.EffectiveAssistantManifest
ProductUserProfile = profiles.ProductUserProfile
product_profile_for_env = profiles.product_profile_for_env
product_profile_from_technical = profiles.product_profile_from_technical


def test_internal_profiles_map_to_exactly_user_or_technical():
    assert product_profile_from_technical("business") is ProductUserProfile.USER
    assert product_profile_from_technical("user") is ProductUserProfile.USER
    assert (
        product_profile_from_technical("developer")
        is ProductUserProfile.TECHNICAL
    )
    assert (
        product_profile_from_technical("technical")
        is ProductUserProfile.TECHNICAL
    )
    assert {item.value for item in ProductUserProfile} == {
        "user",
        "technical",
    }


def test_environment_projection_does_not_create_a_third_profile():
    technical_env = SimpleNamespace(
        user=SimpleNamespace(has_group=lambda xmlid: xmlid == "base.group_system")
    )
    user_env = SimpleNamespace(
        user=SimpleNamespace(has_group=lambda _xmlid: False)
    )

    assert product_profile_for_env(technical_env) is ProductUserProfile.TECHNICAL
    assert product_profile_for_env(user_env) is ProductUserProfile.USER


def test_manifest_keeps_existing_evidence_provider_seam():
    field_names = {item.name for item in fields(EffectiveAssistantManifest)}
    assert "evidence_provider_ids" in field_names
    assert not any("excerpt" in item or "content" in item for item in field_names)
