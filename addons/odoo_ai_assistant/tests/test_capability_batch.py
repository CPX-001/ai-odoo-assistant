import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent import CapabilityPlanError, CapabilityPlanService, PlannedCapability
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilityExecutor,
    CapabilityPolicy,
    clear_discovery_cache,
    discover_capabilities,
)


class TestCapabilityBatchMutations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        system_group = cls.env.ref("base.group_system")
        company = cls.env.company
        cls.batch_user = cls.env["res.users"].create(
            {
                "name": "AI Batch User",
                "login": "ai-batch-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([system_group.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.targets = self.env["res.partner"].create(
            [{"name": "AI BATCH A"}, {"name": "AI BATCH B"}]
        )

    def _runtime(self):
        context = CapabilityContext(
            env=self.env(user=self.batch_user, su=False),
            turn_id="batch-capability-test",
            screen={"model": "res.partner", "selected_ids": self.targets.ids},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "always_confirm",
                    "max_auto_risk": "low",
                    "allow_synthetic_data": False,
                    "synthetic_data_authorized": False,
                    "max_tool_calls_per_turn": 32,
                    "max_write_steps_per_plan": 12,
                    "max_replans": 2,
                    "max_consecutive_failures": 3,
                }
            },
        )
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return context, registry, CapabilityPlanService(registry=registry, executor=executor)

    def _patch_plan(self, *, record_ids=None, name="AI BATCH UPDATED"):
        return (
            PlannedCapability(
                capability="odoo.records.batch_mutate",
                arguments={
                    "operation": "patch",
                    "model": "res.partner",
                    "record_ids": list(record_ids or self.targets.ids),
                    "values": {"name": name},
                },
                summary="Actualizar los contactos seleccionados",
            ),
        )

    def test_batch_patch_preview_policy_barrier_and_verification(self):
        context, registry, plans = self._runtime()
        self.assertFalse(context.env.su)
        self.assertEqual(
            registry.resolve("odoo.records.batch_mutate").source_module,
            "odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.odoo_batch",
        )

        prepared = asyncio.run(plans.prepare(self._patch_plan()))
        self.assertEqual(prepared["state"], "awaiting_confirmation")
        self.assertTrue(prepared["requires_confirmation"])
        preview = prepared["steps"][0]["preview"]
        self.assertEqual(preview["operation"], "patch")
        self.assertEqual(preview["count"], 2)
        self.assertEqual(
            [row["changes"][0]["after"] for row in preview["records"]],
            ["AI BATCH UPDATED", "AI BATCH UPDATED"],
        )
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier_seen = []

        def before_effect():
            self.targets.invalidate_recordset(["name"])
            self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])
            barrier_seen.append(True)

        executed = asyncio.run(
            plans.execute(authorized, human_approved=True, before_effect=before_effect)
        )
        self.assertEqual(barrier_seen, [True])
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(
            self.targets.mapped("name"),
            ["AI BATCH UPDATED", "AI BATCH UPDATED"],
        )
        self.assertEqual(executed.payload["state"], "completed")
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 2)

    def test_batch_patch_without_required_approval_never_crosses_barrier(self):
        _context, _registry, plans = self._runtime()
        prepared = asyncio.run(plans.prepare(self._patch_plan()))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier_seen = []

        with self.assertRaises(CapabilityPlanError) as captured:
            asyncio.run(
                plans.execute(
                    authorized,
                    human_approved=False,
                    before_effect=lambda: barrier_seen.append(True),
                )
            )

        self.assertEqual(captured.exception.code, "capability_plan_approval_required")
        self.assertEqual(barrier_seen, [])
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])

    def test_batch_create_is_bounded_previewed_and_verified(self):
        context, _registry, plans = self._runtime()
        plan = (
            PlannedCapability(
                capability="odoo.records.batch_mutate",
                arguments={
                    "operation": "create",
                    "model": "res.partner",
                    "rows": [
                        {"name": "AI CREATED A"},
                        {"name": "AI CREATED B"},
                    ],
                },
                summary="Crear dos contactos",
            ),
        )
        prepared = asyncio.run(plans.prepare(plan))
        self.assertEqual(prepared["steps"][0]["preview"]["count"], 2)
        self.assertFalse(context.env["res.partner"].search([("name", "like", "AI CREATED %")]))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        record_ids = executed.results[0].data["record_ids"]
        created = context.env["res.partner"].browse(record_ids).exists()
        self.assertEqual(created.mapped("name"), ["AI CREATED A", "AI CREATED B"])
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 2)

    def test_batch_delete_requires_preview_and_verifies_absence(self):
        context, _registry, plans = self._runtime()
        doomed = self.env["res.partner"].create(
            [{"name": "AI DELETE A"}, {"name": "AI DELETE B"}]
        )
        plan = (
            PlannedCapability(
                capability="odoo.records.batch_mutate",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": doomed.ids,
                },
                summary="Eliminar dos contactos",
            ),
        )
        prepared = asyncio.run(plans.prepare(plan))
        self.assertEqual(prepared["steps"][0]["preview"]["count"], 2)
        self.assertEqual(len(doomed.exists()), 2)
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        self.assertFalse(context.env["res.partner"].browse(doomed.ids).exists())
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 2)

    def test_batch_rejects_more_than_fifty_rows(self):
        _context, _registry, plans = self._runtime()
        oversized = self._patch_plan(record_ids=list(range(1, 52)))
        with self.assertRaises(CapabilityError):
            asyncio.run(plans.prepare(oversized))
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])

    def test_partial_invalid_patch_is_rejected_without_any_write(self):
        _context, _registry, plans = self._runtime()
        invalid = self._patch_plan(record_ids=[self.targets[0].id, 2_147_483_647])
        with self.assertRaises(CapabilityError):
            asyncio.run(plans.prepare(invalid))
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])

    def test_record_rule_is_authoritative_for_batch_targets(self):
        self.env["ir.rule"].create(
            {
                "name": "AI batch test deny target",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "domain_force": "[('id', '!=', %d)]" % self.targets[0].id,
                "perm_read": True,
                "perm_write": True,
                "perm_create": False,
                "perm_unlink": True,
            }
        )
        _context, _registry, plans = self._runtime()
        with self.assertRaises(CapabilityError):
            asyncio.run(plans.prepare(self._patch_plan()))
        self.targets.invalidate_recordset(["name"])
        self.assertEqual(self.targets.mapped("name"), ["AI BATCH A", "AI BATCH B"])
