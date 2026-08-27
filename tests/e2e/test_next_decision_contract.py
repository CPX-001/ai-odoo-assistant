"""Dependency-light E2E-1 checks for the strict NextDecision contract."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "addons/odoo_ai_assistant/runtime/agent/contracts.py"
CODEX_DECISION = ROOT / "addons/odoo_ai_assistant/runtime/agent/codex_decision.py"

spec = importlib.util.spec_from_file_location("e2e_next_decision_contract", CONTRACT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestNextDecisionContract(unittest.TestCase):
    def test_exact_union_accepts_one_branch_at_a_time(self):
        self.assertIsInstance(
            module.parse_next_decision(
                {"kind": "final_answer", "answer": "Hola", "confidence": "high"}
            ),
            module.FinalAnswer,
        )
        self.assertIsInstance(
            module.parse_next_decision(
                {
                    "kind": "reasoning_capability_call",
                    "call_id": "call-1",
                    "capability": "odoo.query_records",
                    "arguments": {},
                }
            ),
            module.ReasoningCapabilityCall,
        )
        self.assertIsInstance(
            module.parse_next_decision(
                {
                    "kind": "plan_step_proposal",
                    "call_id": "call-2",
                    "capability": "odoo.record.patch",
                    "arguments": {},
                    "user_summary": "Actualizar registro",
                }
            ),
            module.PlanStepProposal,
        )

    def test_mixed_unknown_or_non_json_decisions_fail_closed(self):
        bad = [
            {"kind": "final_answer", "answer": "x", "confidence": "high", "call_id": "x"},
            {"kind": "unknown"},
            {
                "kind": "reasoning_capability_call",
                "call_id": "bad id",
                "capability": "odoo.query_records",
                "arguments": {},
            },
            {
                "kind": "reasoning_capability_call",
                "call_id": "c1",
                "capability": "QUERY",
                "arguments": {},
            },
            {
                "kind": "reasoning_capability_call",
                "call_id": "c1",
                "capability": "odoo.query_records",
                "arguments": {"bad": object()},
            },
        ]
        for value in bad:
            with self.assertRaises(module.NextDecisionError):
                module.parse_next_decision(value)

    def test_schema_has_three_disjoint_branches(self):
        schema = module.next_decision_schema()
        self.assertEqual(len(schema["oneOf"]), 3)
        self.assertEqual(
            {branch["properties"]["kind"]["const"] for branch in schema["oneOf"]},
            {"final_answer", "reasoning_capability_call", "plan_step_proposal"},
        )

    def test_codex_decision_route_has_no_dynamic_provider_tools(self):
        source = CODEX_DECISION.read_text(encoding="utf-8")
        self.assertIn('"dynamicTools": []', source)
        self.assertIn('"outputSchema": next_decision_schema()', source)
        self.assertIn("return validate_next_decision(", source)
        self.assertNotIn("executor.execute", source)


if __name__ == "__main__":
    unittest.main()
