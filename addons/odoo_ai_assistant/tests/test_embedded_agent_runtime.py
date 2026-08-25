import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent import AgentReasoningResult, AgentTurnService
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)


class _QueryReasoningEngine:
    async def run_agent_turn(
        self,
        *,
        message,
        conversation_summary,
        context,
        reasoning_capabilities,
        planning_capabilities,
        executor,
    ):
        del message, conversation_summary, context, planning_capabilities
        names = {item.name for item in reasoning_capabilities}
        assert {
            "odoo.get_effective_schema",
            "odoo.query_records",
            "odoo.aggregate_records",
        }.issubset(names)
        schema = await executor.execute(
            "odoo.get_effective_schema",
            {"model": "res.partner"},
        )
        aggregate = await executor.execute(
            "odoo.aggregate_records",
            {
                "model": "res.partner",
                "schema_id": schema.data["schema_id"],
                "filter": {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "name",
                            "operator": "contains",
                            "value": "AI EMBEDDED QUERY",
                        }
                    ],
                },
                "metrics": [{"operation": "count", "field": None}],
            },
        )
        count = aggregate.data["groups"][0]["metrics"][0]["value"]
        return AgentReasoningResult(
            answer=f"Visible contacts: {count}",
            confidence="high",
        )


class TestEmbeddedAgentRuntime(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.agent_user = cls.env["res.users"].create(
            {
                "name": "Embedded Agent User",
                "login": "embedded-agent-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.env["res.partner"].create(
            [
                {"name": "AI EMBEDDED QUERY ALPHA"},
                {"name": "AI EMBEDDED QUERY BETA"},
            ]
        )

    def _context(self):
        env = self.env(user=self.agent_user, su=False)
        return CapabilityContext(
            env=env,
            turn_id="embedded-agent-test",
            screen={"model": "res.partner", "selected_ids": []},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "risk_based",
                    "max_auto_risk": "moderate",
                    "max_tool_calls_per_turn": 32,
                    "max_write_steps_per_plan": 12,
                }
            },
        )

    def test_query_provider_executes_directly_under_effective_user(self):
        context = self._context()
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        schema = asyncio.run(
            executor.execute(
                "odoo.get_effective_schema",
                {"model": "res.partner"},
            )
        )
        names = {field["name"] for field in schema.data["fields"]}
        self.assertIn("name", names)
        records = asyncio.run(
            executor.execute(
                "odoo.query_records",
                {
                    "model": "res.partner",
                    "schema_id": schema.data["schema_id"],
                    "fields": ["name"],
                    "filter": {
                        "match": "all",
                        "conditions": [
                            {
                                "field": "name",
                                "operator": "contains",
                                "value": "AI EMBEDDED QUERY",
                            }
                        ],
                    },
                    "order": [{"field": "name", "direction": "asc"}],
                    "limit": 10,
                },
            )
        )
        self.assertEqual(records.data["returned_count"], 2)
        self.assertEqual(
            [item["fields"]["name"] for item in records.data["records"]],
            ["AI EMBEDDED QUERY ALPHA", "AI EMBEDDED QUERY BETA"],
        )
        self.assertFalse(context.env.su)

    def test_agent_turn_service_uses_registry_and_capability_executor(self):
        context = self._context()
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
            reasoning_engine=_QueryReasoningEngine(),
        )
        result = asyncio.run(
            service.run(message="How many matching contacts are visible?")
        )
        self.assertEqual(result.answer, "Visible contacts: 2")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.plan, ())
