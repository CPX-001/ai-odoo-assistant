from __future__ import annotations

import asyncio
from unittest.mock import patch

from odoo import SUPERUSER_ID, Command
from odoo.tests.common import TransactionCase, tagged

from ..runtime.capabilities import (
    CapabilityApproval,
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityPolicy,
    CapabilityRisk,
    clear_discovery_cache,
    discover_capabilities_for_env,
)
from ..runtime.host_broker import HostBrokerClient, _binding_from_durable_plan


@tagged("post_install", "-at_install")
class TestPhase10HostOperations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        internal_group = cls.env.ref("base.group_user")
        system_group = cls.env.ref("base.group_system")
        cls.business_user = cls.env["res.users"].create(
            {
                "name": "Phase 10 Business User",
                "login": "phase10-business-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.technical_user = cls.env["res.users"].create(
            {
                "name": "Phase 10 Technical User",
                "login": "phase10-technical-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id, system_group.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()

    def _context(self, user, *, turn_id="phase10-host-turn", metadata=None):
        env = self.env(user=user, su=False)
        self.assertFalse(env.su)
        return CapabilityContext(
            env=env,
            turn_id=turn_id,
            metadata=metadata or {},
        )

    def test_business_profile_cannot_gain_technical_host_capabilities(self):
        business = self._context(
            self.business_user,
            metadata={
                "capability_policy": {
                    "confirmation_mode": "confirm_protected",
                    "max_auto_risk": "protected",
                }
            },
        )
        registry = discover_capabilities_for_env(business.env)
        with patch.object(HostBrokerClient, "available", return_value=True):
            available = {item.name for item in registry.available(business)}

        for name in (
            "odoo.module.inspect",
            "postgres.health",
            "odoo.config.inspect",
            "odoo.config.patch",
            "host.service.status",
            "host.service.restart",
        ):
            self.assertNotIn(name, available)

    def test_technical_local_diagnostics_do_not_depend_on_broker(self):
        context = self._context(self.technical_user)
        registry = discover_capabilities_for_env(context.env)
        with patch.object(HostBrokerClient, "available", return_value=False):
            available = {item.name for item in registry.available(context)}

        self.assertIn("odoo.module.inspect", available)
        self.assertIn("postgres.health", available)
        self.assertNotIn("odoo.config.inspect", available)
        self.assertNotIn("odoo.config.patch", available)
        self.assertNotIn("host.service.status", available)
        self.assertNotIn("host.service.restart", available)

        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        module = asyncio.run(
            executor.execute("odoo.module.inspect", {"module": "odoo_ai_assistant"})
        ).data
        self.assertEqual(module["module"], "odoo_ai_assistant")
        self.assertEqual(module["state"], "installed")
        self.assertIsInstance(module["dependencies"], tuple)

        postgres = asyncio.run(executor.execute("postgres.health", {})).data
        self.assertTrue(postgres["server_version"])
        self.assertGreaterEqual(postgres["database_size_bytes"], 0)
        self.assertGreaterEqual(postgres["backend_count"], 1)
        self.assertGreaterEqual(postgres["active_backend_count"], 0)
        self.assertGreaterEqual(postgres["waiting_backend_count"], 0)

    def test_broker_effect_definitions_use_existing_host_effect_lifecycle(self):
        context = self._context(self.technical_user)
        registry = discover_capabilities_for_env(context.env)
        with patch.object(HostBrokerClient, "available", return_value=True):
            available = {item.name for item in registry.available(context)}
        self.assertIn("odoo.config.patch", available)
        self.assertIn("host.service.restart", available)

        for name in ("odoo.config.patch", "host.service.restart"):
            definition = registry.resolve(name)
            self.assertEqual(definition.risk, CapabilityRisk.HOST)
            self.assertEqual(definition.effect, CapabilityEffect.HOST)
            self.assertEqual(definition.exposure, CapabilityExposure.PLAN)
            self.assertEqual(definition.approval, CapabilityApproval.POLICY)
            self.assertEqual(definition.required_groups, ("base.group_system",))
            self.assertIsNotNone(definition.preview_handler)
            self.assertIsNotNone(definition.verify_handler)
            self.assertEqual(definition.audit_metadata["recovery_mode"], "external")

    def test_effectful_broker_binding_is_read_from_committed_durable_plan(self):
        arguments = {"target": "odoo", "key": "workers", "value": "4"}
        precondition = "sha256:" + "a" * 64
        binding = "sha256:" + "b" * 64
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).create(
            {
                "turn_uuid": "phase10-binding-turn",
                "user_id": self.technical_user.id,
                "company_id": self.env.company.id,
                "state": "running",
                "capability_plan_payload": {
                    "format_version": 1,
                    "human_approved": True,
                    "plan": {
                        "format_version": 3,
                        "state": "executing",
                        "requires_confirmation": False,
                        "recovery_units": [
                            {
                                "unit_id": "unit-1",
                                "mode": "external",
                                "step_ids": ["step-1"],
                                "state": "executing",
                            }
                        ],
                        "steps": [
                            {
                                "step_id": "step-1",
                                "capability": "odoo.config.patch",
                                "arguments": arguments,
                                "state": "previewed",
                                "binding_fingerprint": binding,
                                "precondition_fingerprint": precondition,
                            }
                        ],
                    },
                },
            }
        )
        context = self._context(self.technical_user, turn_id=turn.turn_uuid)

        self.assertEqual(
            _binding_from_durable_plan(
                context,
                capability="odoo.config.patch",
                arguments=arguments,
            ),
            ("step-1", binding, precondition),
        )
        with self.assertRaisesRegex(CapabilityError, "host_broker_plan_binding_missing"):
            _binding_from_durable_plan(
                context,
                capability="odoo.config.patch",
                arguments={**arguments, "value": "8"},
            )
