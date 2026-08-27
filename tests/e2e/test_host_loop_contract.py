"""Dependency-light E2E-3 tests for the Odoo-owned READ host loop."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "addons" / "odoo_ai_assistant"

# Load the dependency-light runtime below an isolated package namespace. Importing the real addon
# package would execute its Odoo controllers/models ``__init__`` modules and make this standalone
# contract test require an installed Odoo runtime merely during collection.
for package_name, package_path in (
    ("_host_loop_fixture", ADDON),
    ("_host_loop_fixture.runtime", ADDON / "runtime"),
    ("_host_loop_fixture.runtime.agent", ADDON / "runtime" / "agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _host_loop_fixture.runtime.agent.contracts import (  # noqa: E402
    FinalAnswer,
    ReasoningCapabilityCall,
)
from _host_loop_fixture.runtime.agent.service import AgentTurnError, AgentTurnService  # noqa: E402
from _host_loop_fixture.runtime.agent.working_transcript import (  # noqa: E402
    WorkingItem,
    append_working_item,
)
from _host_loop_fixture.runtime.capabilities import (  # noqa: E402
    CapabilityApproval,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityRegistry,
    CapabilityResult,
    CapabilityRisk,
    ExecutionAuthority,
)


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"model": {"type": "string", "minLength": 1}},
    "required": ["model"],
}
_QUERY = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "model": {"type": "string", "minLength": 1},
        "schema_id": {"type": "string", "minLength": 1},
    },
    "required": ["model", "schema_id"],
}
_OUTPUT = {
    "type": "object",
    "additionalProperties": True,
}


def _definition(name, schema):
    return CapabilityDefinition(
        name=name,
        title=name,
        description=f"Test capability {name}",
        input_schema=schema,
        output_schema=_OUTPUT,
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        exposure=CapabilityExposure.REASONING,
        approval=CapabilityApproval.NONE,
        handler=lambda _context, _arguments: {},
        max_calls=4,
    )


class _Savepoint:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        self.cursor.entries += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.exits += 1
        return False


class _Cursor:
    def __init__(self):
        self.entries = 0
        self.exits = 0

    def savepoint(self):
        return _Savepoint(self)


class _Env:
    su = False

    def __init__(self):
        self.cr = _Cursor()


class _DecisionEngine:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.inputs = []

    async def next_decision(self, **kwargs):
        self.inputs.append(kwargs)
        if not self.decisions:
            raise AssertionError("decision sequence exhausted")
        return self.decisions.pop(0)


class _Executor:
    def __init__(self, results=None, errors=None):
        self.results = dict(results or {})
        self.errors = dict(errors or {})
        self.calls = []

    async def execute(self, capability, arguments, *, authority):
        self.calls.append((capability, dict(arguments), authority))
        error = self.errors.get(capability)
        if error:
            raise CapabilityError(error)
        return CapabilityResult(data=dict(self.results.get(capability, {"ok": True})))


class TestHostLoopContract(unittest.TestCase):
    def setUp(self):
        self.env = _Env()
        self.context = CapabilityContext(
            env=self.env,
            turn_id="turn-1",
            metadata={
                "capability_policy": {
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_correctable_failures": 3,
                }
            },
        )
        self.registry = CapabilityRegistry(
            (
                _definition("odoo.get_effective_schema", _SCHEMA),
                _definition("odoo.query_records", _QUERY),
            )
        )

    def _run(self, decisions, *, executor=None, items=(), cancelled=lambda: False):
        engine = _DecisionEngine(decisions)
        executor = executor or _Executor()
        persisted = []

        def persist(value):
            persisted.append(tuple(value))

        service = AgentTurnService(
            registry=self.registry,
            context=self.context,
            executor=executor,
            decision_engine=engine,
            working_items=items,
            persist_working_items=persist,
            cancellation_requested=cancelled,
        )
        result = asyncio.run(service.run(message="test request"))
        return result, service, engine, executor, persisted

    def test_hello_finishes_without_capability_execution(self):
        result, service, engine, executor, persisted = self._run(
            [FinalAnswer("final_answer", "Hola", "high")]
        )
        self.assertEqual(result.answer, "Hola")
        self.assertEqual(result.plan, ())
        self.assertEqual(executor.calls, [])
        self.assertEqual([item.kind for item in service.working_items], ["user_input", "final_answer"])
        self.assertGreaterEqual(len(persisted), 2)
        self.assertEqual(len(engine.inputs), 1)

    def test_multi_read_executes_only_reasoning_authority_and_feeds_results_back(self):
        executor = _Executor(
            results={
                "odoo.get_effective_schema": {"schema_id": "schema-1"},
                "odoo.query_records": {"records": [{"id": 7}]},
            }
        )
        decisions = [
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "call-1",
                "odoo.get_effective_schema",
                {"model": "res.partner"},
            ),
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "call-2",
                "odoo.query_records",
                {"model": "res.partner", "schema_id": "schema-1"},
            ),
            FinalAnswer("final_answer", "Encontrado.", "high"),
        ]
        result, service, engine, executor, _persisted = self._run(
            decisions,
            executor=executor,
        )
        self.assertEqual(result.answer, "Encontrado.")
        self.assertEqual(len(executor.calls), 2)
        self.assertTrue(
            all(call[2] is ExecutionAuthority.REASONING for call in executor.calls)
        )
        self.assertEqual(self.env.cr.entries, 2)
        self.assertEqual(self.env.cr.exits, 2)
        second_input = engine.inputs[1]["working_items"]
        result_items = [item for item in second_input if item["kind"] == "capability_result"]
        self.assertEqual(result_items[-1]["data"]["result"]["schema_id"], "schema-1")
        self.assertEqual(service.working_items[-1].kind, "final_answer")

    def test_schema_invalid_call_is_returned_for_bounded_repair_without_execution(self):
        executor = _Executor(results={"odoo.get_effective_schema": {"schema_id": "schema-1"}})
        decisions = [
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "bad-1",
                "odoo.query_records",
                {"model": "res.partner"},
            ),
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "call-2",
                "odoo.get_effective_schema",
                {"model": "res.partner"},
            ),
            FinalAnswer("final_answer", "Corregido.", "high"),
        ]
        result, service, engine, executor, _persisted = self._run(
            decisions,
            executor=executor,
        )
        self.assertEqual(result.answer, "Corregido.")
        self.assertEqual([item[0] for item in executor.calls], ["odoo.get_effective_schema"])
        errors = [item for item in service.working_items if item.kind == "capability_error"]
        self.assertEqual(errors[0].data["code"], "agent_capability_arguments_invalid")
        self.assertEqual(engine.inputs[1]["working_items"][-1]["kind"], "capability_error")

    def test_access_denied_allows_only_final_explanation_after_host_error(self):
        executor = _Executor(errors={"odoo.get_effective_schema": "access_denied"})
        decisions = [
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "denied-1",
                "odoo.get_effective_schema",
                {"model": "res.partner"},
            ),
            FinalAnswer("final_answer", "No tienes acceso.", "high"),
        ]
        result, service, _engine, executor, _persisted = self._run(
            decisions,
            executor=executor,
        )
        self.assertEqual(result.answer, "No tienes acceso.")
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(
            [item.data.get("code") for item in service.working_items if item.kind == "capability_error"],
            ["access_denied"],
        )

    def test_restart_closes_pending_call_without_reexecuting_same_call_id(self):
        items = append_working_item((), "user_input", {"message": "test request"})
        items = append_working_item(
            items,
            "assistant_decision",
            {
                "decision_kind": "reasoning_capability_call",
                "call_id": "call-old",
                "capability": "odoo.get_effective_schema",
                "arguments": {"model": "res.partner"},
            },
        )
        items = append_working_item(
            items,
            "capability_call",
            {
                "call_id": "call-old",
                "capability": "odoo.get_effective_schema",
                "arguments": {"model": "res.partner"},
            },
        )
        result, service, _engine, executor, _persisted = self._run(
            [FinalAnswer("final_answer", "Reanudado.", "medium")],
            items=items,
        )
        self.assertEqual(result.answer, "Reanudado.")
        self.assertEqual(executor.calls, [])
        error = next(
            item
            for item in service.working_items
            if item.kind == "capability_error" and item.data["call_id"] == "call-old"
        )
        self.assertEqual(error.data["code"], "agent_capability_call_interrupted")

    def test_cancellation_is_checked_before_provider_call(self):
        engine = _DecisionEngine([FinalAnswer("final_answer", "unused", "high")])
        service = AgentTurnService(
            registry=self.registry,
            context=self.context,
            executor=_Executor(),
            decision_engine=engine,
            cancellation_requested=lambda: True,
        )
        with self.assertRaisesRegex(AgentTurnError, "agent_cancelled"):
            asyncio.run(service.run(message="test request"))
        self.assertEqual(engine.inputs, [])

    def test_provider_decision_budget_is_enforced(self):
        limited = CapabilityContext(
            env=self.env,
            turn_id="turn-1",
            metadata={
                "capability_policy": {
                    "max_provider_decisions": 1,
                    "max_capability_calls": 1,
                    "max_consecutive_correctable_failures": 1,
                }
            },
        )
        engine = _DecisionEngine(
            [
                ReasoningCapabilityCall(
                    "reasoning_capability_call",
                    "call-1",
                    "odoo.get_effective_schema",
                    {"model": "res.partner"},
                ),
                FinalAnswer("final_answer", "too late", "high"),
            ]
        )
        service = AgentTurnService(
            registry=self.registry,
            context=limited,
            executor=_Executor(),
            decision_engine=engine,
        )
        with self.assertRaisesRegex(AgentTurnError, "agent_provider_decision_budget_exceeded"):
            asyncio.run(service.run(message="test request"))
        self.assertEqual(len(engine.inputs), 1)


if __name__ == "__main__":
    unittest.main()
