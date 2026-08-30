import asyncio
import json
from pathlib import Path

from odoo.tests.common import BaseCase

from ..runtime.agent.codex import (
    CodexAgentError,
    CodexAgentSettings,
    _model_thread_options,
)
from ..runtime.agent.codex_decision import (
    CodexDecisionEngine,
    _DECISION_INSTRUCTIONS,
    _codex_next_decision_schema,
    _decision_result,
    _is_simple_social_message,
)
from ..runtime.agent.contracts import (
    FinalAnswer,
    ReasoningCapabilityCall,
    TaskPlanUpdate,
)


class _EventClient:
    def __init__(self, *events):
        self.events = list(events)

    async def next_event(self, *, timeout):
        del timeout
        return self.events.pop(0)


class TestCodexDecisionAdapter(BaseCase):
    def test_model_and_reasoning_effort_share_one_bounded_thread_config(self):
        configured = CodexAgentSettings(
            executable=Path("/tmp/codex"),
            codex_home=Path("/tmp/codex-home"),
            model="gpt-5.6-terra",
            reasoning_effort="high",
        )
        defaulted = CodexAgentSettings(
            executable=Path("/tmp/codex"),
            codex_home=Path("/tmp/codex-home"),
        )

        self.assertEqual(
            _model_thread_options(configured),
            {
                "model": "gpt-5.6-terra",
                "config": {"model_reasoning_effort": "high"},
            },
        )
        self.assertEqual(_model_thread_options(defaulted), {})

    def test_wire_schema_wraps_four_neutral_decisions_and_encodes_open_arguments(self):
        schema = _codex_next_decision_schema()

        self.assertEqual(schema["type"], "object")
        self.assertNotIn("oneOf", schema)
        alternatives = schema["properties"]["decision"]["anyOf"]
        self.assertEqual(len(alternatives), 4)
        kinds = {
            branch["properties"]["kind"]["enum"][0]
            for branch in alternatives
        }
        self.assertEqual(
            kinds,
            {
                "final_answer",
                "task_plan_update",
                "reasoning_capability_call",
                "plan_step_proposal",
            },
        )
        task_branch = next(
            branch
            for branch in alternatives
            if branch["properties"]["kind"]["enum"][0] == "task_plan_update"
        )
        self.assertIn("task_plan", task_branch["properties"])
        self.assertNotIn("arguments_json", task_branch["properties"])

        capability_branches = [
            branch
            for branch in alternatives
            if branch["properties"]["kind"]["enum"][0]
            in {"reasoning_capability_call", "plan_step_proposal"}
        ]
        self.assertEqual(len(capability_branches), 2)
        for branch in capability_branches:
            self.assertIn("arguments_json", branch["properties"])
            self.assertNotIn("arguments", branch["properties"])
            self.assertIn("arguments_json", branch["required"])

    def test_simple_social_message_allows_only_one_final_answer_decision(self):
        self.assertTrue(_is_simple_social_message("hola"))
        self.assertTrue(_is_simple_social_message("¡Buenos días!"))
        self.assertTrue(_is_simple_social_message("hello, how are you?"))
        self.assertFalse(_is_simple_social_message("hola, crea una factura"))
        self.assertFalse(_is_simple_social_message("resume este contacto"))

        alternatives = _codex_next_decision_schema(final_answer_only=True)["properties"][
            "decision"
        ]["anyOf"]
        self.assertEqual(len(alternatives), 1)
        self.assertEqual(
            alternatives[0]["properties"]["kind"]["enum"],
            ["final_answer"],
        )

    def test_codex_instructions_keep_task_plan_non_authoritative_and_effect_steps_distinct(self):
        instructions = " ".join(_DECISION_INSTRUCTIONS.split())
        self.assertIn("user-visible TaskPlan", instructions)
        self.assertIn("never grants execution authority", instructions)
        self.assertIn("one distinct plan_step_proposal at a time", instructions)
        self.assertIn("never repeat them", instructions)
        self.assertIn("verified_effect_receipt proves execution", instructions)
        self.assertIn("Return final_answer immediately for greetings", instructions)
        self.assertIn("Never create a TaskPlan merely to restate a one-step request", instructions)

    def test_wire_envelope_is_normalized_to_strict_next_decision(self):
        final = _decision_result(
            {
                "items": [
                    {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "decision": {
                                    "kind": "final_answer",
                                    "answer": "Hola",
                                    "confidence": "high",
                                }
                            }
                        ),
                    }
                ]
            }
        )
        task_plan = _decision_result(
            {
                "items": [
                    {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "decision": {
                                    "kind": "task_plan_update",
                                    "task_plan": {
                                        "goal": "Resolver la petición",
                                        "revision": 1,
                                        "steps": [
                                            {
                                                "step_id": "inspect",
                                                "title": "Inspeccionar contexto",
                                                "state": "in_progress",
                                                "depends_on": [],
                                            }
                                        ],
                                    },
                                }
                            }
                        ),
                    }
                ]
            }
        )
        call = _decision_result(
            {
                "items": [
                    {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "decision": {
                                    "kind": "reasoning_capability_call",
                                    "call_id": "call-1",
                                    "capability": "odoo.query_records",
                                    "arguments_json": '{"limit":1}',
                                }
                            }
                        ),
                    }
                ]
            }
        )

        self.assertEqual(final, FinalAnswer("final_answer", "Hola", "high"))
        self.assertIsInstance(task_plan, TaskPlanUpdate)
        self.assertEqual(task_plan.task_plan.revision, 1)
        self.assertEqual(task_plan.task_plan.steps[0].step_id, "inspect")
        self.assertEqual(
            call,
            ReasoningCapabilityCall(
                "reasoning_capability_call",
                "call-1",
                "odoo.query_records",
                {"limit": 1},
            ),
        )

    def test_real_app_server_invalid_schema_error_keeps_specific_sanitized_code(self):
        upstream_message = json.dumps(
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_json_schema",
                    "message": "schema detail intentionally not persisted",
                    "param": "text.format.schema",
                },
                "status": 400,
            }
        )
        client = _EventClient(
            {
                "method": "error",
                "params": {
                    "error": {
                        "message": upstream_message,
                        "codexErrorInfo": "other",
                        "additionalDetails": None,
                    },
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "willRetry": False,
                },
            }
        )
        engine = CodexDecisionEngine(
            CodexAgentSettings(
                executable=Path("/tmp/codex"),
                codex_home=Path("/tmp/codex-home"),
            )
        )

        with self.assertRaises(CodexAgentError) as caught:
            asyncio.run(
                engine._wait_for_completion(
                    client,
                    thread_id="thread-1",
                    turn_id="turn-1",
                    deadline=10**12,
                )
            )

        self.assertEqual(caught.exception.code, "codex_output_schema_invalid")
