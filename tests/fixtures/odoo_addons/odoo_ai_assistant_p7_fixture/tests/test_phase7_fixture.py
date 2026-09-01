from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    clear_discovery_cache,
    discover_assistant_extensions_for_env,
    discover_capabilities_for_env,
)
from odoo.tests.common import TransactionCase


class TestPhase7Fixture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.limited_user = cls.env["res.users"].create(
            {
                "name": "Phase 7 Limited User",
                "login": "phase7-limited-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        params = self.env["ir.config_parameter"]
        params.set_param("odoo_ai_assistant.capability.fixture.phase7_read_identity.fixture_label", "")
        params.set_param("odoo_ai_assistant.capability_enabled.fixture.phase7_read_identity", "true")
        params.set_param("odoo_ai_assistant.capability_enabled.fixture.phase7_plan_probe", "true")

    def _context(self, env):
        registry = discover_capabilities_for_env(env)
        resolver = CapabilityConfigResolver.from_env(env)
        return registry, CapabilityContext(
            env=env,
            turn_id="phase7-fixture-turn",
            screen={"model": "res.partner", "view_type": "form"},
            metadata={
                "capability_enabled": resolver.availability_overrides(registry.definitions)
            },
        )

    def test_installed_provider_skill_and_context_are_discovered(self):
        registry, context = self._context(self.env)
        self.assertEqual(
            registry.provider_for("fixture.phase7_read_identity"),
            "fixture.phase7",
        )
        extensions = discover_assistant_extensions_for_env(
            self.env,
            capability_registry=registry,
        )
        self.assertEqual(
            [item.skill_id for item in extensions.skills.definitions],
            ["fixture.phase7_skill"],
        )
        self.assertEqual(
            [item.provider_id for item in extensions.context_providers.providers],
            ["fixture.current_screen"],
        )
        self.assertFalse(
            any(
                item.name == "fixture.phase7_read_identity"
                for item in registry.for_reasoning(context)
            )
        )

    def test_missing_configuration_and_permission_are_distinct(self):
        params = self.env["ir.config_parameter"]
        params.set_param(
            "odoo_ai_assistant.capability.fixture.phase7_read_identity.fixture_label",
            "configured",
        )
        limited_env = self.env(user=self.limited_user, su=False)
        self.assertFalse(limited_env.su)
        self.assertFalse(limited_env.user.has_group("base.group_system"))
        registry, context = self._context(limited_env)
        plan_probe = registry.resolve("fixture.phase7_plan_probe")
        self.assertEqual(plan_probe.required_groups, ("base.group_system",))
        self.assertFalse(plan_probe.available_for(context))

        self.assertIn(
            "fixture.phase7_read_identity",
            {item.name for item in registry.for_reasoning(context)},
        )
        self.assertNotIn(
            "fixture.phase7_plan_probe",
            {item.name for item in registry.for_planning(context)},
        )

    def test_explicit_disablement_removes_capability_from_effective_catalog(self):
        params = self.env["ir.config_parameter"]
        params.set_param(
            "odoo_ai_assistant.capability.fixture.phase7_read_identity.fixture_label",
            "configured",
        )
        params.set_param(
            "odoo_ai_assistant.capability_enabled.fixture.phase7_read_identity",
            "false",
        )
        registry, context = self._context(self.env)
        self.assertNotIn(
            "fixture.phase7_read_identity",
            {item.name for item in registry.for_reasoning(context)},
        )

    def test_active_skill_collects_bounded_jit_context(self):
        self.env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.capability.fixture.phase7_read_identity.fixture_label",
            "configured",
        )
        registry, context = self._context(self.env)
        extensions = discover_assistant_extensions_for_env(
            self.env,
            capability_registry=registry,
        )
        active = extensions.activate(
            context,
            capability_names=(
                *[item.name for item in registry.for_reasoning(context)],
                *[item.name for item in registry.for_planning(context)],
            ),
        )
        self.assertEqual([item.skill_id for item in active.skills], ["fixture.phase7_skill"])
        self.assertEqual(len(active.context), 1)
        self.assertEqual(active.context[0].provider_id, "fixture.current_screen")
        self.assertEqual(active.context[0].data["model"], "res.partner")

    def test_admin_manifest_reflects_fixture_and_provider_profile(self):
        self.env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.capability.fixture.phase7_read_identity.fixture_label",
            "configured",
        )
        payload = self.env["res.config.settings"].assistant_effective_manifest()
        names = {item["name"] for item in payload["capabilities"]}
        skills = {item["skill_id"] for item in payload["skills"]}

        self.assertIn("fixture.phase7_read_identity", names)
        self.assertIn("fixture.phase7_plan_probe", names)
        self.assertIn("fixture.phase7_skill", skills)
        self.assertEqual(payload["provider"]["provider_id"], "openai.codex_app_server")
        self.assertEqual(payload["technical_profile"], "developer")
