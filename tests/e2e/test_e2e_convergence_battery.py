"""Dependency-light final convergence battery for the ADR-019 host loop.

This suite freezes the end-to-end host contracts that can be checked without an Odoo runtime.
Executable Odoo behavior is covered by ``addons/odoo_ai_assistant/tests/test_e2e_convergence_battery.py``.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = pathlib.Path(__file__).with_name("e2e_decision_sequences.json")
WORKING = ROOT / "addons/odoo_ai_assistant/runtime/agent/working_transcript.py"
SERVICE = ROOT / "addons/odoo_ai_assistant/runtime/agent/service.py"
OVERLAY = ROOT / "addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py"
PLAN = ROOT / "addons/odoo_ai_assistant/runtime/agent/plan.py"
ACTION_TEST = ROOT / "addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py"

spec = importlib.util.spec_from_file_location("e2e_final_working_transcript", WORKING)
working = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = working
spec.loader.exec_module(working)


class TestE2EConvergenceBattery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.cases = {case["id"]: case for case in payload["cases"]}
        cls.defaults = payload["defaults"]
        cls.service = SERVICE.read_text(encoding="utf-8")
        cls.overlay = OVERLAY.read_text(encoding="utf-8")
        cls.plan = PLAN.read_text(encoding="utf-8")
        cls.action_test = ACTION_TEST.read_text(encoding="utf-8")

    def _decisions(self, case_id):
        return self.cases[case_id]["expected_decisions"]

    def test_hello(self):
        decisions = self._decisions("hello")
        self.assertEqual(decisions, [{"kind": "final_answer"}])
        self.assertEqual(self.cases["hello"]["max_capability_calls"], 0)

    def test_read(self):
        decisions = self._decisions("read_partner")
        self.assertEqual(
            [(item["kind"], item.get("capability")) for item in decisions],
            [
                ("reasoning_capability_call", "odoo.get_effective_schema"),
                ("reasoning_capability_call", "odoo.query_records"),
                ("final_answer", None),
            ],
        )
        self.assertFalse(any(item["kind"] == "plan_step_proposal" for item in decisions))

    def test_multi_read(self):
        decisions = self._decisions("multi_read_synthesis")
        calls = [item for item in decisions if item["kind"] == "reasoning_capability_call"]
        self.assertEqual(len(calls), 4)
        self.assertEqual(decisions[-1]["kind"], "final_answer")
        self.assertLessEqual(len(decisions), self.cases["multi_read_synthesis"]["max_provider_decisions"])

    def test_patch(self):
        decisions = self._decisions("supported_patch")
        self.assertEqual(decisions[-1], {"kind": "plan_step_proposal", "capability": "odoo.record.patch"})
        self.assertIn("allow_plan_proposals=True", self.overlay)
        self.assertIn("prepared = asyncio.run(plans.prepare(result.plan))", self.overlay)
        self.assertNotIn("ExecutionAuthority.PLAN", self.service)

    def test_create(self):
        decisions = self._decisions("supported_create")
        self.assertEqual(decisions[-1], {"kind": "plan_step_proposal", "capability": "odoo.record.create"})
        self.assertIn('search_count([("name", "=", marker)]), 0', self.action_test)
        self.assertIn('search_count([("name", "=", marker)]), 1', self.action_test)

    def test_repairable_errors(self):
        decisions = self._decisions("validation_repair")
        self.assertEqual(decisions[0]["host_result"], "agent_capability_arguments_invalid")
        self.assertEqual(decisions[-1]["kind"], "final_answer")
        self.assertIn('"agent_capability_arguments_invalid"', self.service)
        self.assertIn("agent_correctable_failure_budget_exceeded", self.service)

    def test_access_denied(self):
        decisions = self._decisions("access_denied")
        self.assertEqual(decisions[0]["host_result"], "access_denied")
        self.assertEqual(decisions[-1]["kind"], "final_answer")
        self.assertIn('"access_denied"', self.service)
        self.assertIn("agent_terminal_capability_error_requires_final", self.service)

    def test_unsupported_action(self):
        decisions = self._decisions("unsupported_action")
        self.assertEqual(decisions, [{"kind": "final_answer"}])
        self.assertEqual(self.cases["unsupported_action"]["max_capability_calls"], 0)

    def test_restart_idempotency(self):
        items = working.append_working_item((), "user_input", {"message": "Lee"})
        items = working.append_working_item(
            items,
            "assistant_decision",
            {
                "call_id": "read-1",
                "decision_kind": "reasoning_capability_call",
                "capability": "odoo.query_records",
                "arguments": {},
            },
        )
        items = working.append_working_item(
            items,
            "capability_call",
            {"call_id": "read-1", "capability": "odoo.query_records", "arguments": {}},
        )
        self.assertEqual(working.call_state(items, "read-1"), "pending")
        items = working.append_working_item(
            items,
            "capability_error",
            {"call_id": "read-1", "capability": "odoo.query_records", "code": "agent_capability_call_interrupted"},
        )
        self.assertEqual(working.call_state(items, "read-1"), "completed")
        with self.assertRaises(working.WorkingTranscriptError):
            working.append_working_item(
                items,
                "capability_result",
                {"call_id": "read-1", "capability": "odoo.query_records", "result": {}},
            )
        self.assertIn("_close_interrupted_calls", self.service)
        self.assertIn("agent_working_call_id_duplicate", self.service)

    def test_approval(self):
        self.assertIn('prepared["requires_confirmation"]', self.overlay)
        self.assertIn("self._persist_awaiting_plan(turn, envelope, response)", self.overlay)
        self.assertIn('self.assertEqual(prepared["state"], "awaiting_confirmation")', self.action_test)
        self.assertIn('self.assertTrue(prepared["requires_confirmation"])', self.action_test)

    def test_exactly_once(self):
        self.assertIn("_commit_plan_barrier(", self.overlay)
        self.assertIn('self.assertEqual(barrier, ["crossed"])', self.action_test)
        self.assertIn('search_count([("name", "=", marker)]), 1', self.action_test)
        self.assertIn("agent_working_call_id_duplicate", self.service)

    def test_verification(self):
        execute_at = self.plan.index("result = await self._executor.execute(")
        verify_at = self.plan.index("verification = await self._executor.verify(")
        self.assertLess(execute_at, verify_at)
        self.assertIn('"verified_effect_receipt"', self.overlay)
        self.assertIn('self.assertIsNotNone(executed.payload["steps"][0]["verification"])', self.action_test)


if __name__ == "__main__":
    unittest.main()
