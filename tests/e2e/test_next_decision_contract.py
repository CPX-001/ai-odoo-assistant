"""Dependency-light E2E-1 checks for the strict NextDecision contract."""

from __future__ import annotations

import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADDON = ROOT / "addons" / "odoo_ai_assistant"
CODEX_DECISION = ADDON / "runtime" / "agent" / "codex_decision.py"
SERVICE = ADDON / "runtime" / "agent" / "service.py"

for package_name, package_path in (
    ("_next_decision_fixture", ADDON),
    ("_next_decision_fixture.runtime", ADDON / "runtime"),
    ("_next_decision_fixture.runtime.agent", ADDON / "runtime" / "agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _next_decision_fixture.runtime.agent import contracts as module  # noqa: E402


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
                    "kind": "task_plan_update",
                    "task_plan": {
                        "goal": "Resolver la petición",
                        "revision": 1,
                        "steps": [
                            {
                                "step_id": "inspect",
                                "title": "Inspeccionar contexto",
                                "state": "in_progress",
                                "depends_on": [],
                            }
                        ],
                    },
                }
            ),
            module.TaskPlanUpdate,
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
                "kind": "task_plan_update",
                "task_plan": {
                    "goal": "x",
                    "revision": 0,
                    "steps": [
                        {
                            "step_id": "one",
                            "title": "Uno",
                            "state": "pending",
                            "depends_on": [],
                        }
                    ],
                },
            },
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

    def test_schema_has_four_disjoint_branches(self):
        schema = module.next_decision_schema()
        self.assertEqual(len(schema["oneOf"]), 4)
        self.assertEqual(
            {branch["properties"]["kind"]["const"] for branch in schema["oneOf"]},
            {
                "final_answer",
                "task_plan_update",
                "reasoning_capability_call",
                "plan_step_proposal",
            },
        )

    def test_codex_decision_route_is_tool_free_and_host_revalidates(self):
        source = CODEX_DECISION.read_text(encoding="utf-8")
        host = SERVICE.read_text(encoding="utf-8")
        self.assertIn('"dynamicTools": []', source)
        self.assertIn('"outputSchema": _codex_next_decision_schema(', source)
        self.assertIn("final_answer_only=final_answer_only", source)
        self.assertNotIn("executor.execute", source)
        self.assertIn("return validate_next_decision(", source)
        self.assertIn("decision = validate_next_decision(", host)
        self.assertIn("TaskPlan is progress data only", host)


if __name__ == "__main__":
    unittest.main()
