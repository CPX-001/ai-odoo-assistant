import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.capabilities import (
    CapabilityApproval,
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityDependency,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityRegistry,
    CapabilityRisk,
    CapabilityVerification,
    ExecutionAuthority,
    clear_discovery_cache,
    discover_capabilities,
)
from ..runtime.capabilities.adapters import codex_plan_catalog, codex_reasoning_tools

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _ok_handler(context, arguments):
    del context, arguments
    return {"ok": True}


def _ok_preview(context, arguments):
    del context, arguments
    return CapabilityPreview(
        summary={"operation": "restart", "target": "test-machine"},
        precondition_fingerprint="sha256:" + "0" * 64,
    )


def _ok_verify(context, arguments):
    del arguments
    result = context.metadata.get("capability_result")
    return CapabilityVerification(
        verified=bool(isinstance(result, dict) and result.get("ok") is True),
        summary={"verified": True},
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

    def _context(self, events=None, *, metadata=None):
        env = self.env(user=self.capability_user, su=False)
        sink = None
        if events is not None:

            def sink(event_type, title, payload):
                events.append((event_type, title, dict(payload)))

        return CapabilityContext(
            env=env,
            turn_id="capability-test-turn",
            event_sink=sink,
            metadata=metadata or {},
        )

    def test_provider_is_discovered_without_central_registration(self):
        registry = discover_capabilities()
        definition = registry.resolve("odoo.runtime_identity")
        self.assertEqual(definition.executor_id, "odoo.runtime_identity.v1")
        self.assertEqual(definition.namespace, "odoo")
        self.assertEqual(definition.source_qualname, "runtime_identity")
        descriptor = definition.wire_descriptor()
        self.assertEqual(descriptor["name"], "odoo.runtime_identity")
        self.assertEqual(descriptor["inputSchema"]["type"], "object")
        self.assertEqual(descriptor["meta"]["exposure"], "reasoning")
        self.assertEqual(descriptor["meta"]["approval"], "none")

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

    def test_plan_capability_is_known_but_not_directly_callable(self):
        definition = CapabilityDefinition(
            name="customer.machine.restart",
            title="Restart machine",
            description="Restart one explicitly configured customer machine.",
            input_schema=_EMPTY_SCHEMA,
            output_schema={"type": "object"},
            risk=CapabilityRisk.ACTION,
            effect=CapabilityEffect.EXTERNAL,
            exposure=CapabilityExposure.PLAN,
            approval=CapabilityApproval.ALWAYS,
            handler=_ok_handler,
            preview_handler=_ok_preview,
            verify_handler=_ok_verify,
        )
        registry = CapabilityRegistry((definition,))
        context = self._context()
        self.assertEqual(codex_reasoning_tools(registry, context), ())
        self.assertEqual(codex_plan_catalog(registry, context)[0]["name"], definition.name)
        executor = CapabilityExecutor(
            registry,
            context,
            config=CapabilityConfigResolver(),
        )
        with self.assertRaises(CapabilityError) as captured:
            asyncio.run(executor.execute(definition.name, {}))
        self.assertEqual(captured.exception.code, "capability_authority_mismatch")
        with self.assertRaises(CapabilityError) as captured:
            asyncio.run(
                executor.execute(
                    definition.name,
                    {},
                    authority=ExecutionAuthority.PLAN,
                )
            )
        self.assertEqual(captured.exception.code, "capability_approval_required")
        result = asyncio.run(
            executor.execute(
                definition.name,
                {},
                authority=ExecutionAuthority.PLAN,
                approved=True,
            )
        )
        self.assertTrue(result.data["ok"])

    def test_host_capability_is_never_exposed_to_codex(self):
        definition = CapabilityDefinition(
            name="assistant.maintenance.cleanup",
            description="Internal bounded cleanup.",
            input_schema=_EMPTY_SCHEMA,
            output_schema={"type": "object"},
            risk=CapabilityRisk.HOST,
            effect=CapabilityEffect.HOST,
            exposure=CapabilityExposure.HOST,
            handler=_ok_handler,
        )
        registry = CapabilityRegistry((definition,))
        context = self._context()
        self.assertEqual(codex_reasoning_tools(registry, context), ())
        self.assertEqual(codex_plan_catalog(registry, context), ())
        self.assertEqual(registry.for_host(context), (definition,))

    def test_missing_dependency_is_rejected(self):
        definition = CapabilityDefinition(
            name="customer.invoice_analysis",
            description="Analyze a customer invoice.",
            input_schema=_EMPTY_SCHEMA,
            output_schema={"type": "object"},
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            dependencies=(CapabilityDependency("knowledge.customer_manuals"),),
            handler=_ok_handler,
        )
        with self.assertRaises(CapabilityError) as captured:
            CapabilityRegistry((definition,))
        self.assertEqual(captured.exception.code, "capability_dependency_missing")

    def test_disabled_capability_is_not_advertised(self):
        registry = discover_capabilities()
        context = self._context(
            metadata={"capability_enabled": {"odoo.runtime_identity": False}}
        )
        names = {item.name for item in registry.for_reasoning(context)}
        self.assertNotIn("odoo.runtime_identity", names)
