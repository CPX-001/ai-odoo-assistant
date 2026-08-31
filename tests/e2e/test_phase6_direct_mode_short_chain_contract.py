"""Direct-mode contract: bounded reads/effects do not require a visible TaskPlan."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "addons" / "odoo_ai_assistant"

for package_name, package_path in (
    ("_p6_direct_fixture", ADDON),
    ("_p6_direct_fixture.runtime", ADDON / "runtime"),
    ("_p6_direct_fixture.runtime.agent", ADDON / "runtime" / "agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _p6_direct_fixture.runtime.agent.contracts import PlanStepProposal  # noqa: E402
from _p6_direct_fixture.runtime.agent.planning import (  # noqa: E402
    PlanningDecisionEngine,
    resolve_planning_strategy,
)
from _p6_direct_fixture.runtime.capabilities.contracts import CapabilityContext  # noqa: E402


class _Provider:
    def __init__(self, decision):
        self.decision = decision
        self.working_items = None

    async def next_decision(self, **kwargs):
        self.working_items = kwargs["working_items"]
        return self.decision


class TestPhase6DirectModeShortChainContract(unittest.TestCase):
    def _context(self):
        return CapabilityContext(
            env=object(),
            turn_id="p6-direct-short-chain",
            screen={},
            metadata={
                "planning_strategy": resolve_planning_strategy(
                    "adaptive",
                    message="Si no existe Demo créalo y prepara un presupuesto de prueba",
                    screen={},
                ).payload()
            },
        )

    def test_direct_mode_accepts_effect_proposals_without_visible_task_plan(self):
        first = PlanStepProposal(
            "plan_step_proposal",
            "effect-1",
            "odoo.record.create",
            {"model": "res.partner", "values": {"name": "Demo"}},
            "Crear contacto Demo si procede",
        )
        first_provider = _Provider(first)
        accepted_first = asyncio.run(
            PlanningDecisionEngine(first_provider).next_decision(
                message="Si no existe Demo créalo y prepara un presupuesto de prueba",
                conversation_summary="",
                context=self._context(),
                reasoning_capabilities=(),
                planning_capabilities=(),
                working_items=(),
                remaining_budgets={},
            )
        )
        self.assertIs(accepted_first, first)
        self.assertFalse(first_provider.working_items[-1]["data"]["task_plan_available"])

        second = PlanStepProposal(
            "plan_step_proposal",
            "effect-2",
            "odoo.record.create",
            {"model": "sale.order", "values": {"partner_id": 1}},
            "Crear presupuesto de prueba",
        )
        second_provider = _Provider(second)
        accepted_second = asyncio.run(
            PlanningDecisionEngine(second_provider).next_decision(
                message="Si no existe Demo créalo y prepara un presupuesto de prueba",
                conversation_summary="",
                context=self._context(),
                reasoning_capabilities=(),
                planning_capabilities=(),
                working_items=(
                    {
                        "kind": "capability_result",
                        "data": {
                            "call_id": "read-demo",
                            "capability": "odoo.query_records",
                        },
                    },
                    {
                        "kind": "plan_step_proposed",
                        "data": {
                            "call_id": "effect-1",
                            "capability": "odoo.record.create",
                        },
                    },
                ),
                remaining_budgets={},
            )
        )
        self.assertIs(accepted_second, second)
        self.assertFalse(second_provider.working_items[-1]["data"]["task_plan_available"])


if __name__ == "__main__":
    unittest.main()
