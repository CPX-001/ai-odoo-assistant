"""Dependency-light Phase 6 contracts for TaskPlan, EffectPlan bounds and budgets."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "addons" / "odoo_ai_assistant"

for package_name, package_path in (
    ("_p6_fixture", ADDON),
    ("_p6_fixture.runtime", ADDON / "runtime"),
    ("_p6_fixture.runtime.agent", ADDON / "runtime" / "agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _p6_fixture.runtime.agent.budgets import (  # noqa: E402
    AgentBudgetError,
    resolve_agent_budgets,
)
from _p6_fixture.runtime.agent.task_plan import (  # noqa: E402
    TaskPlanError,
    parse_task_plan,
)


class _Context:
    def __init__(self, *, policy=None, budgets=None):
        self.metadata = {
            "capability_policy": dict(policy or {}),
            "agent_budgets": dict(budgets or {}),
        }


class TestPhase6PlanningContract(unittest.TestCase):
    def test_task_plan_is_visible_structured_progress_without_effect_authority(self):
        plan = parse_task_plan(
            {
                "goal": "Diagnosticar y resolver el problema",
                "revision": 2,
                "steps": [
                    {
                        "step_id": "inspect",
                        "title": "Inspeccionar configuración",
                        "state": "completed",
                        "depends_on": [],
                    },
                    {
                        "step_id": "compare",
                        "title": "Comparar evidencia",
                        "state": "in_progress",
                        "depends_on": ["inspect"],
                    },
                    {
                        "step_id": "resolve",
                        "title": "Preparar resolución",
                        "state": "pending",
                        "depends_on": ["compare"],
                    },
                ],
            }
        )

        self.assertEqual(plan.revision, 2)
        self.assertEqual(plan.steps[1].depends_on, ("inspect",))
        payload = plan.payload()
        self.assertEqual(payload["goal"], "Diagnosticar y resolver el problema")
        self.assertNotIn("capability", payload)
        self.assertNotIn("arguments", payload)
        self.assertNotIn("approval", payload)

    def test_task_plan_rejects_forward_dependencies_and_unknown_states(self):
        bad = [
            {
                "goal": "x",
                "revision": 1,
                "steps": [
                    {
                        "step_id": "first",
                        "title": "Primero",
                        "state": "pending",
                        "depends_on": ["later"],
                    },
                    {
                        "step_id": "later",
                        "title": "Luego",
                        "state": "pending",
                        "depends_on": [],
                    },
                ],
            },
            {
                "goal": "x",
                "revision": 1,
                "steps": [
                    {
                        "step_id": "first",
                        "title": "Primero",
                        "state": "executing_effect",
                        "depends_on": [],
                    }
                ],
            },
        ]
        for value in bad:
            with self.assertRaises(TaskPlanError):
                parse_task_plan(value)

    def test_legacy_callers_remain_single_step_until_host_opts_in(self):
        legacy = resolve_agent_budgets(
            _Context(
                policy={
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_correctable_failures": 3,
                    "max_write_steps_per_plan": 12,
                }
            )
        )
        self.assertEqual(legacy.safety.max_effect_steps, 1)

        product = resolve_agent_budgets(
            _Context(
                policy={
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_correctable_failures": 3,
                    "max_write_steps_per_plan": 12,
                    "max_effect_steps_per_plan": 5,
                }
            )
        )
        self.assertEqual(product.safety.max_effect_steps, 5)

    def test_budget_families_apply_independent_host_ceilings(self):
        budgets = resolve_agent_budgets(
            _Context(
                policy={
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_failures": 3,
                    "max_write_steps_per_plan": 12,
                    "max_effect_steps_per_plan": 5,
                },
                budgets={
                    "safety": {"max_effect_steps": 3},
                    "exploration": {
                        "max_provider_decisions": 8,
                        "max_capability_calls": 7,
                    },
                    "cost": {"max_provider_decisions": 4},
                    "latency": {"max_provider_decisions": 6},
                    "response": {
                        "max_transcript_bytes": 64 * 1024,
                        "max_result_bytes": 16 * 1024,
                    },
                },
            )
        )

        self.assertEqual(budgets.provider_decision_limit, 4)
        remaining = budgets.remaining(
            provider_decisions=1,
            capability_calls=2,
            consecutive_failures=1,
            transcript_bytes=1024,
            effect_steps=2,
        )
        self.assertEqual(remaining["provider_decisions"], 3)
        self.assertEqual(remaining["capability_calls"], 5)
        self.assertEqual(remaining["correctable_failures"], 2)
        self.assertEqual(remaining["effect_steps"], 1)
        self.assertEqual(remaining["cost_provider_decisions"], 3)
        self.assertEqual(remaining["latency_provider_decisions"], 5)
        self.assertEqual(remaining["result_bytes"], 16 * 1024)

    def test_effect_step_ceiling_cannot_be_raised_above_five(self):
        with self.assertRaises(AgentBudgetError):
            resolve_agent_budgets(
                _Context(
                    policy={
                        "max_write_steps_per_plan": 12,
                        "max_effect_steps_per_plan": 6,
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
