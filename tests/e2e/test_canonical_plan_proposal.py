"""E2E-4 contract checks for one canonical stage-only PLAN proposal.

The executable TransactionCase coverage lives in the addon test suite. This file is a
dependency-light source/contract gate that can run outside an Odoo checkout.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "addons/odoo_ai_assistant/runtime/agent/contracts.py"
SERVICE = ROOT / "addons/odoo_ai_assistant/runtime/agent/service.py"
OVERLAY = ROOT / "addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py"
PLAN = ROOT / "addons/odoo_ai_assistant/runtime/agent/plan.py"

spec = importlib.util.spec_from_file_location("e2e4_contracts", CONTRACT)
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)


class TestCanonicalPlanProposal(unittest.TestCase):
    def test_plan_proposal_is_one_strict_decision_branch(self):
        decision = contracts.parse_next_decision(
            {
                "kind": "plan_step_proposal",
                "call_id": "plan-1",
                "capability": "odoo.record.patch",
                "arguments": {
                    "model": "res.partner",
                    "record_id": 42,
                    "values": {"phone": "+34 600 000 000"},
                },
                "user_summary": "Actualizar teléfono",
            }
        )
        self.assertIsInstance(decision, contracts.PlanStepProposal)
        self.assertEqual(decision.call_id, "plan-1")
        self.assertEqual(decision.capability, "odoo.record.patch")

    def test_active_host_loop_enables_plan_proposals_without_provider_tool_execution(self):
        source = OVERLAY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("allow_plan_proposals=True", source)
        self.assertIn("prepared = asyncio.run(plans.prepare(result.plan))", source)
        self.assertIn("_append_plan_prepared(service.working_items, prepared)", source)
        self.assertIn('"plan_step_proposed"', service)
        self.assertNotIn("ExecutionAuthority.PLAN", service)

    def test_plan_preparation_uses_existing_capability_plan_service(self):
        source = PLAN.read_text(encoding="utf-8")
        self.assertIn("preview = await self._executor.preview(", source)
        self.assertIn("approval_required = self._executor.approval_required", source)
        self.assertIn("precondition_fingerprint", source)
        self.assertIn("binding_fingerprint", source)

    def test_effect_path_keeps_barrier_execute_and_verify_order(self):
        source = OVERLAY.read_text(encoding="utf-8")
        plan_source = PLAN.read_text(encoding="utf-8")
        barrier = source.index("_commit_plan_barrier(")
        execute = source.index("executed = await plans.execute(")
        receipt = source.index('"verified_effect_receipt"')
        self.assertLess(barrier, execute)
        self.assertLess(execute, receipt)
        self.assertIn("result = await self._executor.execute(", plan_source)
        self.assertIn("verification = await self._executor.verify(", plan_source)
        self.assertLess(
            plan_source.index("result = await self._executor.execute("),
            plan_source.index("verification = await self._executor.verify("),
        )

    def test_verified_receipt_and_plan_result_share_current_transaction(self):
        source = OVERLAY.read_text(encoding="utf-8")
        self.assertIn('"capability_plan_payload": completed', source)
        self.assertIn('"working_items_payload": transcript_payload(receipt_items)', source)
        self.assertIn('"verified": True', source)
        tail = source[source.index("receipt_items = append_working_item("):]
        self.assertNotIn(".commit()", tail)


if __name__ == "__main__":
    unittest.main()
