import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent import CapabilityPlanService, PlannedCapability
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    clear_discovery_cache,
    discover_capabilities,
)


class TestBulkSelectionAndDeletion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = [
            cls.env.ref("base.group_user").id,
            cls.env.ref("base.group_partner_manager").id,
            cls.env.ref("base.group_system").id,
        ]
        cls.bulk_user = cls.env["res.users"].create(
            {
                "name": "AI Bulk User",
                "login": "ai-bulk-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set(groups)],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.targets = self.env["res.partner"].create(
            [{"name": f"AI BULK DELETE {index:03d}"} for index in range(113)]
        )

    def _runtime(self):
        context = CapabilityContext(
            env=self.env(user=self.bulk_user, su=False),
            turn_id="bulk-selection-test",
            screen={"model": "res.partner"},
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
        return context, registry, executor, CapabilityPlanService(registry=registry, executor=executor)

    def test_113_records_are_selected_and_deleted_without_50_row_model_chunking(self):
        context, registry, executor, plans = self._runtime()
        self.assertIsNotNone(registry.resolve("odoo.query_record_ids"))
        self.assertIsNotNone(registry.resolve("odoo.records.bulk_delete"))

        schema = asyncio.run(
            executor.execute("odoo.get_effective_schema", {"model": "res.partner"})
        )
        selected = asyncio.run(
            executor.execute(
                "odoo.query_record_ids",
                {
                    "model": "res.partner",
                    "schema_id": schema.data["schema_id"],
                    "filter": {
                        "match": "all",
                        "conditions": [
                            {
                                "field": "name",
                                "operator": "contains",
                                "value": "AI BULK DELETE",
                            }
                        ],
                    },
                    "limit": 500,
                },
            )
        )
        self.assertEqual(selected.data["returned_count"], 113)
        self.assertFalse(selected.data["truncated"])
        self.assertEqual(set(selected.data["record_ids"]), set(self.targets.ids))

        plan = (
            PlannedCapability(
                capability="odoo.records.bulk_delete",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": selected.data["record_ids"],
                },
                summary="Eliminar los contactos seleccionados",
            ),
        )
        prepared = asyncio.run(plans.prepare(plan))
        preview = prepared["steps"][0]["preview"]
        self.assertEqual(preview["count"], 113)
        self.assertEqual(len(preview["records"]), 25)
        self.assertEqual(preview["omitted_count"], 88)
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(len(self.targets.exists()), 113)

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        self.assertFalse(context.env["res.partner"].browse(self.targets.ids).exists())
        self.assertEqual(executed.results[0].data["count"], 113)
        self.assertNotIn("record_ids", executed.results[0].data)
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 113)
