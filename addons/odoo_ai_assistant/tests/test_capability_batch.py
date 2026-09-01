import asyncio
from types import SimpleNamespace

from odoo import Command, fields
from odoo.tests.common import TransactionCase

from ..models.embedded_runtime import _browser_capability_plan
from ..runtime.agent import (
    CapabilityPlanError,
    CapabilityPlanService,
    PlannedCapability,
)
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
        internal_group = cls.env.ref("base.group_user")
        partner_manager_group = cls.env.ref("base.group_partner_manager")
        sales_manager_group = cls.env.ref("sales_team.group_sale_manager")
        company = cls.env.company
        cls.batch_user = cls.env["res.users"].create(
            {
                "name": "AI Batch User",
                "login": "ai-batch-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [
                    Command.set(
                        [
                            internal_group.id,
                            partner_manager_group.id,
                            sales_manager_group.id,
                            system_group.id,
                        ]
                    )
                ],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.semantic_events = []
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
            event_sink=lambda event_type, title, payload: self.semantic_events.append(
                (event_type, title, dict(payload))
            ),
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
                capability="odoo.records.batch_patch",
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
            registry.resolve("odoo.records.batch_patch").source_module,
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
                capability="odoo.records.batch_create",
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
        preview_started = next(
            payload
            for event_type, _title, payload in self.semantic_events
            if event_type == "tool.preview.started"
        )
        self.assertEqual(
            preview_started["semantic"]["headline_code"], "activity.prepare.create"
        )
        self.assertEqual(preview_started["semantic"]["headline_args"]["count"], 2)
        self.assertFalse(context.env["res.partner"].search([("name", "like", "AI CREATED %")]))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        record_ids = executed.results[0].data["record_ids"]
        created = context.env["res.partner"].browse(record_ids).exists()
        self.assertEqual(created.mapped("name"), ["AI CREATED A", "AI CREATED B"])
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 2)
        verified = next(
            payload
            for event_type, _title, payload in self.semantic_events
            if event_type == "tool.verify.completed"
        )
        self.assertEqual(verified["semantic"]["progress"], {"current": 2, "total": 2})
        self.assertEqual(
            verified["semantic"]["result_summary"]["code"], "activity.result.verified"
        )

        browser_plan = _browser_capability_plan(
            SimpleNamespace(
                turn_uuid="batch-capability-browser-test",
                input_message="Crear dos contactos",
            ),
            executed.payload,
            {
                "confirmation_mode": "always_confirm",
                "max_auto_risk": "low",
                "allow_synthetic_data": False,
            },
        )
        receipt = browser_plan["steps"][0]["receipt"]
        self.assertEqual(receipt["outcome"], "verified")
        self.assertIsNone(receipt["record_id"])
        self.assertEqual(receipt["record_model"], "res.partner")

    def test_batch_create_normalizes_iso_utc_datetime_before_odoo_create(self):
        context, _registry, plans = self._runtime()
        plan = (
            PlannedCapability(
                capability="odoo.records.batch_create",
                arguments={
                    "operation": "create",
                    "model": "sale.order",
                    "rows": [
                        {
                            "partner_id": self.targets[0].id,
                            "date_order": "2026-09-01T15:04:04Z",
                        }
                    ],
                },
                summary="Crear un presupuesto con fecha UTC",
            ),
        )

        prepared = asyncio.run(plans.prepare(plan))
        self.assertEqual(
            prepared["steps"][0]["preview"]["rows"][0]["date_order"],
            "2026-09-01 15:04:04",
        )
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        record_id = executed.results[0].data["record_ids"][0]
        quotation = context.env["sale.order"].browse(record_id).exists()

        self.assertTrue(quotation)
        self.assertEqual(
            fields.Datetime.to_string(quotation.date_order),
            "2026-09-01 15:04:04",
        )

    def test_related_create_workflow_resolves_prior_batch_records_in_one_plan_step(self):
        context, registry, plans = self._runtime()
        self.assertIsNotNone(registry.resolve("odoo.workflow.batch_create_graph"))
        plan = (
            PlannedCapability(
                capability="odoo.workflow.batch_create_graph",
                arguments={
                    "operation": "create_graph",
                    "steps": [
                        {
                            "step_id": "contacts",
                            "model": "res.partner",
                            "rows": [
                                {"name": "AI WORKFLOW CONTACT A"},
                                {"name": "AI WORKFLOW CONTACT B"},
                            ],
                        },
                        {
                            "step_id": "quotations",
                            "model": "sale.order",
                            "rows": [
                                {
                                    "partner_id": {
                                        "$ref": {"step": "contacts", "record_index": 0}
                                    }
                                },
                                {
                                    "partner_id": {
                                        "$ref": {"step": "contacts", "record_index": 1}
                                    }
                                },
                                {
                                    "partner_id": {
                                        "$ref": {"step": "contacts", "record_index": 0}
                                    }
                                },
                            ],
                        },
                    ],
                },
                summary="Crear contactos y presupuestos relacionados",
            ),
        )

        prepared = asyncio.run(plans.prepare(plan))
        preview = prepared["steps"][0]["preview"]
        self.assertEqual(preview["operation"], "create_graph")
        self.assertEqual(preview["count"], 5)
        self.assertEqual(
            [(step["model"], step["count"]) for step in preview["steps"]],
            [("res.partner", 2), ("sale.order", 3)],
        )
        self.assertFalse(
            context.env["res.partner"].search([("name", "like", "AI WORKFLOW CONTACT %")])
        )

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        outcome = executed.results[0].data
        contact_ids = outcome["steps"][0]["record_ids"]
        quotation_ids = outcome["steps"][1]["record_ids"]
        quotations = context.env["sale.order"].browse(quotation_ids).exists()

        self.assertEqual(outcome["total_count"], 5)
        self.assertEqual(quotations.mapped("partner_id").ids, [contact_ids[0], contact_ids[1]])
        self.assertEqual(
            quotations.mapped("partner_id").mapped("name"),
            ["AI WORKFLOW CONTACT A", "AI WORKFLOW CONTACT B"],
        )
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 5)

    def test_related_create_workflow_rejects_forward_and_wrong_relation_references(self):
        _context, _registry, plans = self._runtime()
        invalid = (
            PlannedCapability(
                capability="odoo.workflow.batch_create_graph",
                arguments={
                    "operation": "create_graph",
                    "steps": [
                        {
                            "step_id": "contacts",
                            "model": "res.partner",
                            "rows": [{"name": "AI INVALID WORKFLOW CONTACT"}],
                        },
                        {
                            "step_id": "orders",
                            "model": "sale.order",
                            "rows": [
                                {
                                    "pricelist_id": {
                                        "$ref": {"step": "contacts", "record_index": 0}
                                    }
                                }
                            ],
                        },
                    ],
                },
                summary="No ejecutar una referencia incompatible",
            ),
        )

        with self.assertRaises(CapabilityError) as captured:
            asyncio.run(plans.prepare(invalid))
        self.assertEqual(captured.exception.code, "workflow_reference_invalid")

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
                "domain_force": f"[('id', '!=', {self.targets[0].id})]",
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
