import json

from odoo.tests.common import TransactionCase

from ..runtime.agent import AgentReasoningResult, PlannedCapability
from ..runtime.agent.codex import (
    CodexAgentError,
    _BASE_INSTRUCTIONS,
    _dynamic_tools,
    _planning_transport_name,
    _reconcile_staged_plan,
    _turn_input,
)
from ..runtime.capabilities import CapabilityContext, discover_capabilities


class TestCodexPlanningContract(TransactionCase):
    def _context(self, *, event_sink=None):
        env = self.env(user=self.env.ref("base.user_admin"), su=False)
        return CapabilityContext(
            env=env,
            turn_id="codex-planning-contract",
            screen={"model": "res.partner", "selected_ids": []},
            event_sink=event_sink,
            metadata={
                "capability_policy": {
                    "confirmation_mode": "risk_based",
                    "max_auto_risk": "moderate",
                    "max_tool_calls_per_turn": 32,
                    "max_write_steps_per_plan": 12,
                }
            },
        )

    def test_explicit_supported_mutation_uses_plan_staging_contract(self):
        instructions = " ".join(_BASE_INSTRUCTIONS.split())
        self.assertIn("Planning is an output obligation", instructions)
        self.assertIn("STAGE PLAN ONLY", instructions)
        self.assertIn("calling one never executes, approves, previews or mutates Odoo", instructions)
        self.assertIn("call exactly one matching STAGE PLAN ONLY tool", instructions)
        self.assertIn("approval is exclusively host policy", instructions)

    def test_patch_is_disclosed_as_bounded_plan_capability_and_staging_tool(self):
        context = self._context()
        registry = discover_capabilities()
        reasoning = registry.for_reasoning(context)
        planning = registry.for_planning(context)
        payload = json.loads(
            _turn_input(
                message="Update the selected partner phone number.",
                conversation_summary="",
                context=context,
                reasoning=reasoning,
                planning=planning,
            )
        )

        descriptors = {
            item["name"]: item for item in payload["host_contract"]["planning_catalog"]
        }
        patch = descriptors["odoo.record.patch"]
        self.assertEqual(patch["meta"]["exposure"], "plan")
        self.assertEqual(patch["meta"]["risk"], "write")
        self.assertEqual(patch["meta"]["approval"], "policy")
        self.assertEqual(
            set(patch["inputSchema"]["required"]),
            {"model", "record_id", "values"},
        )

        tools, bindings = _dynamic_tools(reasoning, planning)
        transport = _planning_transport_name("odoo.record.patch")
        staged = next(tool for tool in tools if tool["name"] == transport)
        self.assertEqual(bindings[transport], ("planning", "odoo.record.patch"))
        self.assertTrue(staged["description"].startswith("STAGE PLAN ONLY."))
        self.assertEqual(staged["inputSchema"], patch["inputSchema"])
        self.assertFalse(context.env.su)

    def test_single_staged_patch_recovers_zero_step_structured_result(self):
        events = []
        context = self._context(
            event_sink=lambda event_type, title, payload: events.append(
                (event_type, title, dict(payload))
            )
        )
        staged = (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={
                    "model": "res.partner",
                    "record_id": 42,
                    "values": {"phone": "+34 600 000 000"},
                },
                summary="Update Odoo record",
            ),
        )
        structured = AgentReasoningResult(
            answer="Cambio preparado.",
            confidence="high",
            plan=(),
        )

        reconciled = _reconcile_staged_plan(structured, staged, context)

        self.assertEqual(reconciled.plan, staged)
        diagnostics = [event for event in events if event[0] == "diagnostic.planning"]
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(
            diagnostics[0][2],
            {
                "point": "final_plan_reconciled",
                "structured_plan_count": 0,
                "staged_plan_count": 1,
                "final_plan_count": 1,
                "source": "staged_fallback",
            },
        )

    def test_conflicting_structured_and_staged_plans_fail_closed(self):
        context = self._context()
        staged = (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={"model": "res.partner", "record_id": 42, "values": {"phone": "A"}},
                summary="Update Odoo record",
            ),
        )
        structured = AgentReasoningResult(
            answer="Cambio preparado.",
            confidence="high",
            plan=(
                PlannedCapability(
                    capability="odoo.record.patch",
                    arguments={
                        "model": "res.partner",
                        "record_id": 42,
                        "values": {"phone": "B"},
                    },
                    summary="Update Odoo record",
                ),
            ),
        )

        with self.assertRaisesRegex(CodexAgentError, "codex_plan_output_mismatch"):
            _reconcile_staged_plan(structured, staged, context)
