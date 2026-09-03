import asyncio
from types import SimpleNamespace

from odoo.tests.common import BaseCase

from ..runtime.agent.codex_streaming import (
    _emit_answer_delta,
    _emit_reasoning_summary_delta,
    _emit_streaming_diagnostic,
)
from ..runtime.agent.contracts import FinalAnswer, TaskPlanUpdate
from ..runtime.agent.planning import PlanningDecisionEngine
from ..runtime.agent.service import AgentTurnService
from ..runtime.agent.task_plan import TaskPlan, TaskPlanStep
from ..runtime.agent.telemetry import emit_optional_telemetry
from ..runtime.capabilities import CapabilityContext, CapabilityRegistry


class _DecisionEngine:
    def __init__(self, *decisions):
        self.decisions = list(decisions)

    async def next_decision(self, **_kwargs):
        return self.decisions.pop(0)


class _FailingTelemetryContext:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def emit(self, event_type, title, payload=None):
        self.calls.append((event_type, title, payload))
        raise self.error


class TestOptionalAgentTelemetry(BaseCase):
    def test_failed_provider_timing_sink_does_not_replace_the_decision(self):
        telemetry_calls = []

        def fail_telemetry(event_type, title, payload):
            telemetry_calls.append((event_type, title, dict(payload)))
            raise RuntimeError("telemetry unavailable")

        expected = FinalAnswer("final_answer", "Decisión conservada", "high")
        context = CapabilityContext(
            env=SimpleNamespace(su=False),
            turn_id="optional-provider-timing",
            event_sink=fail_telemetry,
        )

        result = asyncio.run(
            PlanningDecisionEngine(_DecisionEngine(expected)).next_decision(
                context=context,
                working_items=(),
            )
        )

        self.assertEqual(result, expected)
        self.assertEqual(len(telemetry_calls), 1)
        self.assertEqual(telemetry_calls[0][0], "diagnostic.provider.decision")

    def test_failed_streaming_sinks_degrade_without_aborting_the_turn(self):
        context = _FailingTelemetryContext(RuntimeError("stream unavailable"))

        self.assertFalse(_emit_answer_delta(context, "Respuesta provisional"))
        _emit_streaming_diagnostic(
            context,
            "diagnostic.streaming.started",
            chars=21,
        )
        self.assertFalse(
            _emit_reasoning_summary_delta(
                context,
                item_id="reasoning-1",
                summary_index=0,
                text="Resumen legible",
            )
        )

        self.assertEqual(
            [event_type for event_type, _title, _payload in context.calls],
            [
                "answer.delta",
                "diagnostic.streaming.started",
                "reasoning.summary.delta",
            ],
        )

    def test_task_plan_event_failure_does_not_change_the_final_result(self):
        telemetry_calls = []

        def fail_telemetry(event_type, title, payload):
            telemetry_calls.append((event_type, title, dict(payload)))
            raise RuntimeError("telemetry unavailable")

        context = CapabilityContext(
            env=SimpleNamespace(su=False),
            turn_id="optional-task-plan-telemetry",
            event_sink=fail_telemetry,
        )
        task_plan = TaskPlan(
            goal="Resolver la solicitud",
            revision=1,
            revision_kind="initial",
            steps=(
                TaskPlanStep("inspect", "Comprobar datos", "completed"),
                TaskPlanStep(
                    "answer",
                    "Preparar respuesta",
                    "in_progress",
                    ("inspect",),
                ),
            ),
        )
        service = AgentTurnService(
            registry=CapabilityRegistry(()),
            context=context,
            executor=object(),
            decision_engine=_DecisionEngine(
                TaskPlanUpdate("task_plan_update", task_plan),
                FinalAnswer("final_answer", "Respuesta conservada", "high"),
            ),
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Resuelve esto"))

        self.assertEqual(result.answer, "Respuesta conservada")
        self.assertEqual(result.task_plan, task_plan)
        self.assertEqual(len(telemetry_calls), 1)
        self.assertEqual(telemetry_calls[0][0], "task_plan.updated")

    def test_optional_telemetry_does_not_swallow_base_exception(self):
        context = _FailingTelemetryContext(KeyboardInterrupt())

        with self.assertRaises(KeyboardInterrupt):
            emit_optional_telemetry(context, "reasoning.failed", "Falló")

        self.assertEqual(len(context.calls), 1)

        streaming_context = _FailingTelemetryContext(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            _emit_answer_delta(streaming_context, "Respuesta provisional")
        self.assertEqual(len(streaming_context.calls), 1)

    def test_optional_telemetry_does_not_hide_authoritative_flush_failure(self):
        calls = []

        def fail_flush():
            raise RuntimeError("authoritative write invalid")

        context = SimpleNamespace(
            env=SimpleNamespace(cr=SimpleNamespace(flush=fail_flush)),
            emit=lambda *_args: calls.append(True),
        )

        with self.assertRaisesRegex(RuntimeError, "authoritative write invalid"):
            emit_optional_telemetry(context, "reasoning.started", "Procesando")
        self.assertEqual(calls, [])
