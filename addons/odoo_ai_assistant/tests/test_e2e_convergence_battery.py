"""Executable Odoo battery for the final ADR-019 convergence slice."""

from __future__ import annotations

import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent.contracts import FinalAnswer, PlanStepProposal, ReasoningCapabilityCall
from ..runtime.agent.plan import CapabilityPlanService
from ..runtime.agent.service import AgentTurnError, AgentTurnService
from ..runtime.agent.working_transcript import append_working_item
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityPolicy,
    CapabilityRegistry,
    CapabilityRisk,
    clear_discovery_cache,
    discover_capabilities,
)


class _SequenceDecisionEngine:
    def __init__(self, *decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def next_decision(self, **_kwargs):
        self.calls += 1
        if not self._decisions:
            raise AssertionError("unexpected provider decision request")
        return self._decisions.pop(0)


class _FailIfCalledEngine:
    async def next_decision(self, **_kwargs):
        raise AssertionError("provider must not be called for a terminal resumed turn")


class TestE2EConvergenceBattery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        groups = [
            cls.env.ref("base.group_user").id,
            cls.env.ref("base.group_partner_manager").id,
            cls.env.ref("base.group_system").id,
        ]
        cls.agent_user = cls.env["res.users"].create(
            {
                "name": "E2E Convergence Agent",
                "login": "e2e-convergence-agent",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set(groups)],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.target = self.env["res.partner"].create({"name": "E2E FINAL ORIGINAL"})

    def _context(self, turn_id="e2e-final"):
        return CapabilityContext(
            env=self.env(user=self.agent_user, su=False),
            turn_id=turn_id,
            screen={"model": "res.partner", "res_id": self.target.id},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "always_confirm",
                    "max_auto_risk": "low",
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_correctable_failures": 3,
                    "max_write_steps_per_plan": 12,
                }
            },
        )

    def _read_runtime(self):
        counters = {"one": 0, "two": 0, "denied": 0}

        def read_one(_context, arguments):
            counters["one"] += 1
            return {"value": f"one:{arguments['key']}"}

        def read_two(_context, arguments):
            counters["two"] += 1
            return {"value": f"two:{arguments['key']}"}

        def denied(_context, _arguments):
            counters["denied"] += 1
            raise CapabilityError("access_denied")

        input_schema = {
            "type": "object",
            "properties": {"key": {"type": "string", "minLength": 1}},
            "required": ["key"],
            "additionalProperties": False,
        }
        output_schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        definitions = (
            CapabilityDefinition(
                name="test.read_one",
                description="Read one deterministic test value.",
                input_schema=input_schema,
                output_schema=output_schema,
                risk=CapabilityRisk.READ,
                effect=CapabilityEffect.READ_ONLY,
                handler=read_one,
            ),
            CapabilityDefinition(
                name="test.read_two",
                description="Read a second deterministic test value.",
                input_schema=input_schema,
                output_schema=output_schema,
                risk=CapabilityRisk.READ,
                effect=CapabilityEffect.READ_ONLY,
                handler=read_two,
            ),
            CapabilityDefinition(
                name="test.denied",
                description="Return a sanitized access denial for host-loop testing.",
                input_schema=input_schema,
                output_schema=output_schema,
                risk=CapabilityRisk.READ,
                effect=CapabilityEffect.READ_ONLY,
                handler=denied,
            ),
        )
        context = self._context("e2e-final-read")
        registry = CapabilityRegistry(definitions)
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return counters, context, registry, executor

    def _run_read(self, decisions, *, working_items=(), message="Lee"):
        counters, context, registry, executor = self._read_runtime()
        engine = _SequenceDecisionEngine(*decisions)
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
            working_items=working_items,
        )
        result = asyncio.run(service.run(message=message))
        return result, service, engine, counters

    def _action_runtime(self):
        context = self._context("e2e-final-action")
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        plans = CapabilityPlanService(registry=registry, executor=executor)
        return context, registry, executor, plans

    def _propose(self, capability, arguments, summary):
        context, registry, executor, plans = self._action_runtime()
        engine = _SequenceDecisionEngine(
            PlanStepProposal("plan_step_proposal", "plan-1", capability, arguments, summary)
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
            allow_plan_proposals=True,
        )
        result = asyncio.run(service.run(message=summary))
        return context, plans, engine, result

    def _prepared_patch(self):
        context, plans, engine, result = self._propose(
            "odoo.record.patch",
            {
                "model": "res.partner",
                "record_id": self.target.id,
                "values": {"name": "E2E FINAL UPDATED"},
            },
            "Actualizar contacto",
        )
        prepared = asyncio.run(plans.prepare(result.plan))
        return context, plans, engine, prepared

    def test_hello(self):
        result, _service, engine, counters = self._run_read(
            [FinalAnswer("final_answer", "Hola", "high")],
            message="Hola",
        )
        self.assertEqual(result.answer, "Hola")
        self.assertEqual(engine.calls, 1)
        self.assertEqual(counters, {"one": 0, "two": 0, "denied": 0})

    def test_read(self):
        result, _service, _engine, counters = self._run_read(
            [
                ReasoningCapabilityCall("reasoning_capability_call", "r1", "test.read_one", {"key": "A"}),
                FinalAnswer("final_answer", "Leído", "high"),
            ]
        )
        self.assertEqual(result.answer, "Leído")
        self.assertEqual(counters["one"], 1)

    def test_multi_read(self):
        _result, _service, _engine, counters = self._run_read(
            [
                ReasoningCapabilityCall("reasoning_capability_call", "r1", "test.read_one", {"key": "A"}),
                ReasoningCapabilityCall("reasoning_capability_call", "r2", "test.read_two", {"key": "B"}),
                FinalAnswer("final_answer", "Sintetizado", "high"),
            ]
        )
        self.assertEqual(counters["one"], 1)
        self.assertEqual(counters["two"], 1)

    def test_repairable_error(self):
        _result, service, _engine, counters = self._run_read(
            [
                ReasoningCapabilityCall("reasoning_capability_call", "bad-1", "test.read_one", {}),
                ReasoningCapabilityCall("reasoning_capability_call", "good-1", "test.read_one", {"key": "fixed"}),
                FinalAnswer("final_answer", "Reparado", "high"),
            ]
        )
        self.assertEqual(counters["one"], 1)
        errors = [item for item in service.working_items if item.kind == "capability_error"]
        self.assertEqual(errors[0].data["code"], "agent_capability_arguments_invalid")

    def test_access_denied(self):
        result, service, _engine, counters = self._run_read(
            [
                ReasoningCapabilityCall("reasoning_capability_call", "deny-1", "test.denied", {"key": "x"}),
                FinalAnswer("final_answer", "No tengo acceso.", "high"),
            ]
        )
        self.assertEqual(result.answer, "No tengo acceso.")
        self.assertEqual(counters["denied"], 1)
        errors = [item for item in service.working_items if item.kind == "capability_error"]
        self.assertEqual(errors[-1].data["code"], "access_denied")

    def test_unsupported_action(self):
        result, _service, engine, counters = self._run_read(
            [FinalAnswer("final_answer", "Esa acción no está disponible.", "high")],
            message="Haz una acción no soportada",
        )
        self.assertFalse(result.plan)
        self.assertEqual(engine.calls, 1)
        self.assertEqual(sum(counters.values()), 0)

    def test_restart_idempotency(self):
        working = append_working_item((), "user_input", {"message": "Lee"})
        working = append_working_item(
            working,
            "assistant_decision",
            {
                "call_id": "r1",
                "decision_kind": "reasoning_capability_call",
                "capability": "test.read_one",
                "arguments": {"key": "A"},
            },
        )
        working = append_working_item(
            working,
            "capability_call",
            {"call_id": "r1", "capability": "test.read_one", "arguments": {"key": "A"}},
        )
        result, service, _engine, counters = self._run_read(
            [FinalAnswer("final_answer", "Recuperado", "high")],
            working_items=working,
        )
        self.assertEqual(result.answer, "Recuperado")
        self.assertEqual(counters["one"], 0)
        interrupted = [
            item for item in service.working_items
            if item.kind == "capability_error" and item.data.get("call_id") == "r1"
        ]
        self.assertEqual(interrupted[-1].data["code"], "agent_capability_call_interrupted")

        terminal = append_working_item((), "user_input", {"message": "Hola"})
        terminal = append_working_item(
            terminal, "final_answer", {"answer": "Persistido", "confidence": "high"}
        )
        counters2, context2, registry2, executor2 = self._read_runtime()
        service2 = AgentTurnService(
            registry=registry2,
            context=context2,
            executor=executor2,
            decision_engine=_FailIfCalledEngine(),
            working_items=terminal,
        )
        resumed = asyncio.run(service2.run(message="Hola"))
        self.assertEqual(resumed.answer, "Persistido")
        self.assertEqual(sum(counters2.values()), 0)

    def test_patch(self):
        _context, plans, engine, result = self._propose(
            "odoo.record.patch",
            {"model": "res.partner", "record_id": self.target.id, "values": {"name": "E2E FINAL UPDATED"}},
            "Actualizar contacto",
        )
        self.assertEqual(engine.calls, 1)
        self.assertEqual(result.plan[0].capability, "odoo.record.patch")
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "E2E FINAL ORIGINAL")
        prepared = asyncio.run(plans.prepare(result.plan))
        self.assertEqual(prepared["state"], "awaiting_confirmation")
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "E2E FINAL ORIGINAL")

    def test_create(self):
        marker = "E2E FINAL CREATE"
        context, plans, engine, result = self._propose(
            "odoo.record.create",
            {"model": "res.partner", "values": {"name": marker}},
            "Crear contacto",
        )
        self.assertEqual(engine.calls, 1)
        self.assertEqual(context.env["res.partner"].search_count([("name", "=", marker)]), 0)
        prepared = asyncio.run(plans.prepare(result.plan))
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(context.env["res.partner"].search_count([("name", "=", marker)]), 0)

    def test_approval(self):
        _context, _plans, _engine, prepared = self._prepared_patch()
        self.assertEqual(prepared["state"], "awaiting_confirmation")
        self.assertTrue(prepared["requires_confirmation"])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "E2E FINAL ORIGINAL")

    def test_exactly_once(self):
        _context, plans, _engine, prepared = self._prepared_patch()
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier = []
        asyncio.run(
            plans.execute(
                authorized,
                human_approved=True,
                before_effect=lambda: barrier.append("crossed"),
            )
        )
        self.assertEqual(barrier, ["crossed"])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "E2E FINAL UPDATED")

        counters, context, registry, executor = self._read_runtime()
        engine = _SequenceDecisionEngine(
            ReasoningCapabilityCall("reasoning_capability_call", "same", "test.read_one", {"key": "A"}),
            ReasoningCapabilityCall("reasoning_capability_call", "same", "test.read_one", {"key": "A"}),
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
        )
        with self.assertRaises(AgentTurnError) as captured:
            asyncio.run(service.run(message="Lee dos veces"))
        self.assertEqual(captured.exception.code, "agent_working_call_id_duplicate")
        self.assertEqual(counters["one"], 1)

    def test_verification(self):
        _context, plans, _engine, prepared = self._prepared_patch()
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(
            plans.execute(authorized, human_approved=True, before_effect=lambda: None)
        )
        verification = executed.payload["steps"][0]["verification"]
        self.assertIsNotNone(verification)
        self.assertEqual(verification["model"], "res.partner")
        self.assertEqual(verification["record_id"], self.target.id)
