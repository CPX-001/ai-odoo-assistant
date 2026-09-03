import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..models.embedded_runtime_host_loop import _append_prepare_error
from ..runtime.agent.contracts import FinalAnswer, ReasoningCapabilityCall
from ..runtime.agent.plan import CapabilityPlanStepError
from ..runtime.agent.service import AgentTurnService
from ..runtime.agent.working_transcript import append_working_item
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)


class _ReadDecisionEngine:
    def __init__(self, *, repair_first=False):
        self.repair_first = repair_first
        self.step = 0

    async def next_decision(self, *, working_items, **_kwargs):
        self.step += 1
        if self.repair_first and self.step == 1:
            return ReasoningCapabilityCall(
                "reasoning_capability_call",
                "repair-1",
                "odoo.query_records",
                {"model": "res.partner"},
            )
        results = [
            item["data"]
            for item in working_items
            if item.get("kind") == "capability_result"
        ]
        if not results:
            return ReasoningCapabilityCall(
                "reasoning_capability_call",
                f"schema-{self.step}",
                "odoo.get_effective_schema",
                {"model": "res.partner"},
            )
        schema_results = [
            item["result"]
            for item in results
            if item.get("capability") == "odoo.get_effective_schema"
        ]
        query_results = [
            item["result"]
            for item in results
            if item.get("capability") == "odoo.query_records"
        ]
        if not query_results:
            schema_id = schema_results[-1]["schema_id"]
            return ReasoningCapabilityCall(
                "reasoning_capability_call",
                f"query-{self.step}",
                "odoo.query_records",
                {
                    "model": "res.partner",
                    "schema_id": schema_id,
                    "fields": ["name"],
                    "filter": {
                        "match": "all",
                        "conditions": [
                            {
                                "field": "name",
                                "operator": "contains",
                                "value": "AI HOST LOOP",
                            }
                        ],
                    },
                    "order": [{"field": "name", "direction": "asc"}],
                    "limit": 10,
                },
            )
        count = query_results[-1]["returned_count"]
        return FinalAnswer("final_answer", f"Visible contacts: {count}", "high")


class TestHostLoopAgentRuntime(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.agent_user = cls.env["res.users"].create(
            {
                "name": "Host Loop Agent User",
                "login": "host-loop-agent-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.env["res.partner"].create(
            [
                {"name": "AI HOST LOOP ALPHA"},
                {"name": "AI HOST LOOP BETA"},
            ]
        )

    def _run(self, *, repair_first=False):
        env = self.env(user=self.agent_user, su=False)
        context = CapabilityContext(
            env=env,
            turn_id="host-loop-odoo-test",
            screen={"model": "res.partner", "selected_ids": []},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "risk_based",
                    "max_auto_risk": "moderate",
                    "max_provider_decisions": 6,
                    "max_capability_calls": 4,
                    "max_consecutive_correctable_failures": 3,
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
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=_ReadDecisionEngine(repair_first=repair_first),
        )
        return context, service, asyncio.run(service.run(message="Count matching contacts"))

    def test_read_host_loop_uses_effective_user_and_authoritative_results(self):
        context, service, result = self._run()
        self.assertFalse(context.env.su)
        self.assertEqual(result.answer, "Visible contacts: 2")
        self.assertEqual(result.plan, ())
        self.assertEqual(
            [item.kind for item in service.working_items],
            [
                "user_input",
                "assistant_decision",
                "capability_call",
                "capability_result",
                "assistant_decision",
                "capability_call",
                "capability_result",
                "final_answer",
            ],
        )

    def test_invalid_query_is_repaired_without_executing_invalid_arguments(self):
        _context, service, result = self._run(repair_first=True)
        self.assertEqual(result.answer, "Visible contacts: 2")
        errors = [item for item in service.working_items if item.kind == "capability_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].data["code"], "agent_capability_arguments_invalid")
        self.assertEqual(errors[0].data["capability"], "odoo.query_records")

    def test_prepare_failure_becomes_no_effect_repair_evidence(self):
        items = append_working_item((), "user_input", {"message": "Eliminar contactos"})
        error = CapabilityPlanStepError(
            "action_rejected",
            step_id="delete-1",
            capability="odoo.records.bulk_delete",
            phase="prepare",
            details={"model": "res.partner", "exception_type": "RedirectWarning"},
        )

        repaired = _append_prepare_error(items, error)

        evidence = repaired[-1]
        self.assertEqual(evidence.kind, "plan_execution_error")
        self.assertEqual(evidence.data["phase"], "prepare")
        self.assertEqual(evidence.data["effect_state"], "none")
        self.assertFalse(evidence.data["rolled_back"])
        self.assertEqual(evidence.data["details"]["model"], "res.partner")
