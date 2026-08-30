"""Dependency-light Phase 6.2 planning-mode and evidence-driven replan contracts."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "addons" / "odoo_ai_assistant"

for package_name, package_path in (
    ("_p62_fixture", ADDON),
    ("_p62_fixture.runtime", ADDON / "runtime"),
    ("_p62_fixture.runtime.agent", ADDON / "runtime" / "agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _p62_fixture.runtime.agent.contracts import ReasoningCapabilityCall  # noqa: E402
from _p62_fixture.runtime.agent.decision_validation import (  # noqa: E402
    NextDecisionValidationError,
)
from _p62_fixture.runtime.agent.planning import (  # noqa: E402
    PlanningDecisionEngine,
    resolve_planning_strategy,
    validate_task_plan_transition,
)
from _p62_fixture.runtime.agent.task_plan import (  # noqa: E402
    TaskPlan,
    TaskPlanStep,
    parse_task_plan,
    task_plan_schema,
)
from _p62_fixture.runtime.capabilities.contracts import CapabilityContext  # noqa: E402


class _Provider:
    def __init__(self, decision):
        self.decision = decision
        self.working_items = None

    async def next_decision(self, **kwargs):
        self.working_items = kwargs["working_items"]
        return self.decision


class TestPhase6AdaptivePlanningContract(unittest.TestCase):
    def test_adaptive_and_deliberate_are_host_modes_not_authority_profiles(self):
        adaptive = resolve_planning_strategy(
            "adaptive",
            message="Revisa este contacto",
            screen={"selected_ids": []},
        )
        deliberate = resolve_planning_strategy(
            "deliberate",
            message="Revisa este contacto",
            screen={"selected_ids": []},
        )

        self.assertEqual(adaptive.effective_mode, "adaptive")
        self.assertFalse(adaptive.task_plan_required)
        self.assertEqual(deliberate.effective_mode, "deliberate")
        self.assertTrue(deliberate.task_plan_required)
        self.assertNotIn("approval", deliberate.payload())
        self.assertNotIn("capability", deliberate.payload())

    def test_auto_uses_bounded_structural_complexity_only(self):
        simple = resolve_planning_strategy(
            "auto",
            message="Resume el contacto",
            screen={"selected_ids": []},
        )
        complex_request = resolve_planning_strategy(
            "auto",
            message=(
                "1. Revisa los datos y las restricciones.\n"
                "2. Contrasta los registros seleccionados.\n"
                "3. Explica las diferencias y prepara una resolución.\n"
                "4. Verifica los resultados antes de concluir."
            ),
            screen={"selected_ids": [1, 2]},
        )

        self.assertEqual(simple.effective_mode, "adaptive")
        self.assertEqual(complex_request.effective_mode, "deliberate")
        self.assertGreaterEqual(complex_request.complexity_score, 4)

    def test_current_task_plan_schema_exposes_public_revision_semantics(self):
        schema = task_plan_schema()
        self.assertEqual(
            set(schema["required"]),
            {"goal", "revision", "revision_kind", "revision_summary", "steps"},
        )
        self.assertNotIn("capability", schema["properties"])
        self.assertNotIn("arguments", schema["properties"])
        self.assertEqual(
            set(schema["properties"]["revision_kind"]["enum"]),
            {"initial", "progress", "replan"},
        )

    def test_deliberate_requires_task_plan_before_first_capability_request(self):
        provider = _Provider(
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "read-1",
                "odoo.query_records",
                {},
            )
        )
        engine = PlanningDecisionEngine(provider)
        context = CapabilityContext(
            env=object(),
            turn_id="p62-deliberate",
            screen={},
            metadata={
                "planning_strategy": resolve_planning_strategy(
                    "deliberate", message="Investiga", screen={}
                ).payload()
            },
        )

        with self.assertRaises(NextDecisionValidationError) as captured:
            asyncio.run(
                engine.next_decision(
                    message="Investiga",
                    conversation_summary="",
                    context=context,
                    reasoning_capabilities=(),
                    planning_capabilities=(),
                    working_items=(),
                    remaining_budgets={},
                )
            )

        self.assertEqual(captured.exception.code, "agent_task_plan_required")
        self.assertEqual(provider.working_items[-1]["kind"], "host_planning_strategy")
        self.assertEqual(
            provider.working_items[-1]["data"]["effective_mode"],
            "deliberate",
        )

    def test_progress_revision_cannot_silently_change_structure(self):
        initial = TaskPlan(
            goal="Resolver",
            revision=1,
            steps=(TaskPlanStep("inspect", "Inspeccionar", "in_progress"),),
            revision_kind="initial",
        )
        working = ({"kind": "task_plan", "data": initial.payload()},)
        changed = TaskPlan(
            goal="Resolver",
            revision=2,
            steps=(TaskPlanStep("replace", "Cambiar enfoque", "in_progress"),),
            revision_kind="progress",
        )

        with self.assertRaises(NextDecisionValidationError) as captured:
            validate_task_plan_transition(changed, working)
        self.assertEqual(captured.exception.code, "agent_task_plan_replan_required")

    def test_structural_replan_requires_new_host_evidence(self):
        initial = TaskPlan(
            goal="Resolver",
            revision=1,
            steps=(TaskPlanStep("inspect", "Inspeccionar", "in_progress"),),
            revision_kind="initial",
        )
        replan = TaskPlan(
            goal="Resolver",
            revision=2,
            steps=(TaskPlanStep("verify", "Verificar otra hipótesis", "in_progress"),),
            revision_kind="replan",
            revision_summary="La evidencia anterior descartó la primera hipótesis.",
        )
        base = ({"kind": "task_plan", "data": initial.payload()},)

        with self.assertRaises(NextDecisionValidationError) as captured:
            validate_task_plan_transition(replan, base)
        self.assertEqual(captured.exception.code, "agent_task_plan_replan_without_evidence")

        validate_task_plan_transition(
            replan,
            (
                *base,
                {
                    "kind": "capability_result",
                    "data": {"call_id": "read-1", "capability": "odoo.query_records"},
                },
            ),
        )

    def test_legacy_persisted_task_plan_remains_readable(self):
        plan = parse_task_plan(
            {
                "goal": "Resolver",
                "revision": 1,
                "steps": [
                    {
                        "step_id": "one",
                        "title": "Inspeccionar",
                        "state": "in_progress",
                        "depends_on": [],
                    }
                ],
            }
        )

        self.assertEqual(plan.effective_revision_kind, "initial")
        self.assertEqual(plan.revision_summary, "")


if __name__ == "__main__":
    unittest.main()
