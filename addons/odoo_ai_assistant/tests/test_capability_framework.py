import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.capabilities import (
    CapabilityContext,
    CapabilityError,
    CapabilityExecutor,
    CapabilityRegistry,
    clear_discovery_cache,
    discover_capabilities,
)


class TestCapabilityFramework(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.capability_user = cls.env["res.users"].create(
            {
                "name": "AI Capability User",
                "login": "ai-capability-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()

    def _context(self, events=None):
        env = self.env(user=self.capability_user, su=False)
        sink = None
        if events is not None:
            sink = lambda event_type, title, payload: events.append(
                (event_type, title, dict(payload))
            )
        return CapabilityContext(
            env=env,
            turn_id="capability-test-turn",
            event_sink=sink,
        )

    def test_provider_is_discovered_without_central_registration(self):
        registry = discover_capabilities()
        definition = registry.resolve("odoo.runtime_identity")
        self.assertEqual(definition.executor_id, "odoo.runtime_identity.v1")
        self.assertEqual(definition.source_qualname, "runtime_identity")
        descriptor = definition.wire_descriptor()
        self.assertEqual(descriptor["name"], "odoo.runtime_identity")
        self.assertEqual(descriptor["inputSchema"]["type"], "object")

    def test_uniform_executor_runs_under_effective_odoo_user(self):
        events = []
        context = self._context(events)
        executor = CapabilityExecutor(discover_capabilities(), context)
        result = asyncio.run(executor.execute("odoo.runtime_identity", {}))
        self.assertEqual(result.data["uid"], self.capability_user.id)
        self.assertEqual(result.data["company_id"], context.env.company.id)
        self.assertFalse(context.env.su)
        self.assertEqual(
            [event[0] for event in events],
            ["tool.started", "tool.completed"],
        )

    def test_schema_validation_rejects_unadvertised_arguments(self):
        executor = CapabilityExecutor(discover_capabilities(), self._context())
        with self.assertRaises(CapabilityError) as captured:
            asyncio.run(
                executor.execute(
                    "odoo.runtime_identity",
                    {"unexpected": "value"},
                )
            )
        self.assertEqual(captured.exception.code, "capability_input_invalid")

    def test_duplicate_capability_names_are_rejected(self):
        definition = discover_capabilities().resolve("odoo.runtime_identity")
        with self.assertRaises(CapabilityError) as captured:
            CapabilityRegistry((definition, definition))
        self.assertEqual(captured.exception.code, "capability_name_duplicate")
