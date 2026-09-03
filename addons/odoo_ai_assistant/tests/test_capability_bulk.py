import asyncio
import json

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
from ..runtime.capabilities.providers.odoo_bulk import _compact_delete_results
from ..runtime.capabilities.validation import validate_payload


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
        self.assertEqual(executed.results[0].data["outcome"], "completed")
        self.assertEqual(executed.results[0].data["failed_count"], 0)
        self.assertEqual(executed.results[0].data["excluded_count"], 0)
        self.assertEqual(executed.results[0].data["failed_record_ids"], [])
        self.assertEqual(executed.results[0].data["excluded_record_ids"], [])
        self.assertNotIn("record_ids", executed.results[0].data)
        self.assertEqual(executed.payload["steps"][0]["verification"]["count"], 113)

    def test_protected_company_and_active_user_contacts_remain_explicitly_excluded(self):
        context, _registry, _executor, plans = self._runtime()
        protected_ids = [context.env.company.partner_id.id, self.bulk_user.partner_id.id]
        requested_ids = [*self.targets.ids, *protected_ids]
        requested = (
            PlannedCapability(
                capability="odoo.records.bulk_delete",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": requested_ids,
                },
                summary="Eliminar contactos eliminables",
            ),
        )

        prepared = asyncio.run(plans.prepare(requested))
        preview = prepared["steps"][0]["preview"]
        self.assertEqual(preview["requested_count"], 115)
        self.assertEqual(preview["count"], 113)
        self.assertEqual(preview["excluded_count"], 2)
        self.assertEqual(
            {item["record_id"] for item in preview["protected_records"]},
            set(protected_ids),
        )

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        self.assertFalse(context.env["res.partner"].browse(self.targets.ids).exists())
        remaining_protected = context.env["res.partner"].browse(protected_ids).exists()
        self.assertEqual(set(remaining_protected.ids), set(protected_ids))
        self.assertEqual(executed.results[0].data["requested_count"], 115)
        self.assertEqual(executed.results[0].data["count"], 113)
        self.assertEqual(executed.results[0].data["excluded_count"], 2)
        self.assertEqual(executed.results[0].data["failed_count"], 0)
        self.assertEqual(executed.results[0].data["outcome"], "partial")
        self.assertEqual(
            set(executed.results[0].data["excluded_record_ids"]),
            set(protected_ids),
        )
        self.assertEqual(
            {group["error_code"] for group in executed.results[0].data["retained_groups"]},
            {"protected_company_partner", "protected_linked_active_user"},
        )
        self.assertEqual(
            executed.payload["steps"][0]["verification"],
            {
                "operation": "delete",
                "model": "res.partner",
                "outcome": "partial",
                "count": 113,
                "requested_count": 115,
                "failed_count": 0,
                "excluded_count": 2,
            },
        )

    def test_referenced_record_is_retained_while_unrelated_records_are_deleted(self):
        _context, _registry, _executor, plans = self._runtime()
        requested = self.targets[:3]
        blocked = requested[1]
        quotation = self.env["sale.order"].create({"partner_id": blocked.id})
        plan = (
            PlannedCapability(
                capability="odoo.records.bulk_delete",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": requested.ids,
                },
                summary="Eliminar contactos eliminables",
            ),
        )

        prepared = asyncio.run(plans.prepare(plan))
        self.assertEqual(prepared["steps"][0]["preview"]["count"], 3)
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        result = executed.results[0].data

        self.assertEqual(set(requested.exists().ids), {blocked.id})
        self.assertTrue(quotation.exists())
        self.assertEqual(result["outcome"], "partial")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["excluded_count"], 0)
        self.assertEqual(result["failed_record_ids"], [blocked.id])
        self.assertEqual(result["excluded_record_ids"], [])
        self.assertEqual(result["omitted_retained_count"], 0)
        self.assertEqual(len(result["retained_groups"]), 1)
        failure = result["retained_groups"][0]
        self.assertEqual(failure["state"], "failed")
        self.assertEqual(failure["error_code"], "record_is_referenced")
        self.assertNotIn("blocking_model", failure)
        self.assertEqual(failure["record_ids"], [blocked.id])
        self.assertNotIn("constraint", failure)
        self.assertEqual(
            executed.payload["steps"][0]["verification"]["failed_count"],
            1,
        )

    def test_per_record_unlink_rule_does_not_block_other_visible_records(self):
        denied, allowed = self.targets[:2]
        self.env["ir.rule"].create(
            {
                "name": "AI bulk test deny one unlink target",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "domain_force": f"[('id', '!=', {denied.id})]",
                "perm_read": False,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": True,
            }
        )
        context, _registry, _executor, plans = self._runtime()
        plan = (
            PlannedCapability(
                capability="odoo.records.bulk_delete",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": [denied.id, allowed.id],
                },
                summary="Eliminar contactos permitidos",
            ),
        )

        prepared = asyncio.run(plans.prepare(plan))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        result = executed.results[0].data

        self.assertTrue(context.env["res.partner"].browse(denied.id).exists())
        self.assertFalse(context.env["res.partner"].browse(allowed.id).exists())
        self.assertEqual(result["outcome"], "partial")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["failed_record_ids"], [denied.id])
        self.assertEqual(result["retained_groups"][0]["error_code"], "access_denied")

    def test_only_protected_records_produces_blocked_verified_outcome(self):
        context, _registry, _executor, plans = self._runtime()
        protected_ids = [context.env.company.partner_id.id, self.bulk_user.partner_id.id]
        plan = (
            PlannedCapability(
                capability="odoo.records.bulk_delete",
                arguments={
                    "operation": "delete",
                    "model": "res.partner",
                    "record_ids": protected_ids,
                },
                summary="Conservar contactos operativos protegidos",
            ),
        )

        prepared = asyncio.run(plans.prepare(plan))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(plans.execute(authorized, human_approved=True))
        result = executed.results[0].data

        remaining = context.env["res.partner"].browse(protected_ids).exists()
        self.assertEqual(set(remaining.ids), set(protected_ids))
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["excluded_count"], 2)
        self.assertEqual(
            executed.payload["steps"][0]["verification"]["outcome"],
            "blocked",
        )

    def test_worst_case_compact_failure_receipt_stays_below_tool_budget(self):
        _context, registry, _executor, _plans = self._runtime()
        definition = registry.resolve("odoo.records.bulk_delete")
        raw = [
            {
                "record_id": 2_147_000_000 + index,
                "state": "failed",
                "error_code": f"business_rule_{index % 10}",
                "message": f"{index % 10}" + ("🧪" * 159),
                "resolution": "r" * 64,
                "blocking_model": f"x.{str(index % 10) * 126}",
            }
            for index in range(500)
        ]
        payload = {
            "operation": "delete",
            "model": "x.bulk",
            "outcome": "blocked",
            "count": 0,
            "requested_count": 500,
            "excluded_count": 0,
            "failed_count": 500,
            **_compact_delete_results(raw),
            "selection_fingerprint": f"sha256:{'a' * 64}",
            "content_trust": "untrusted",
        }

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self.assertLessEqual(len(encoded), definition.max_output_bytes)
        validate_payload(
            payload,
            definition.output_schema,
            max_bytes=definition.max_output_bytes,
            error_code="capability_output_invalid",
        )

    def test_approval_is_reused_only_for_same_operation_record_subset(self):
        _context, _registry, _executor, plans = self._runtime()

        def prepared(record_ids):
            return asyncio.run(
                plans.prepare(
                    (
                        PlannedCapability(
                            capability="odoo.records.bulk_delete",
                            arguments={
                                "operation": "delete",
                                "model": "res.partner",
                                "record_ids": record_ids,
                            },
                            summary="Eliminar contactos eliminables",
                        ),
                    )
                )
            )

        approved = prepared(self.targets.ids[:3])
        narrowed = prepared(self.targets.ids[:2])
        expanded = prepared([*self.targets.ids[:3], self.env.company.partner_id.id])

        self.assertTrue(plans.approval_refines(approved, narrowed))
        self.assertFalse(plans.approval_refines(approved, expanded))
