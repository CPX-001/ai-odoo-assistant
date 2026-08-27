import asyncio
import json
from pathlib import Path

from odoo.tests.common import BaseCase

from ..runtime.agent.codex import CodexAgentError, CodexAgentSettings
from ..runtime.agent.codex_decision import (
    CodexDecisionEngine,
    _codex_next_decision_schema,
    _decision_result,
)
from ..runtime.agent.contracts import FinalAnswer, ReasoningCapabilityCall


class _EventClient:
    def __init__(self, *events):
        self.events = list(events)

    async def next_event(self, *, timeout):
        del timeout
        return self.events.pop(0)


class TestCodexDecisionAdapter(BaseCase):
    def test_wire_schema_wraps_union_and_encodes_open_arguments(self):
        schema = _codex_next_decision_schema()

        self.assertEqual(schema["type"], "object")
        self.assertNotIn("oneOf", schema)
        alternatives = schema["properties"]["decision"]["anyOf"]
        self.assertEqual(len(alternatives), 3)
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
