import asyncio
from pathlib import Path

from odoo.tests.common import BaseCase

from ..runtime.agent.codex import CodexAgentError, CodexAgentSettings
from ..runtime.agent.codex_streaming import (
    StreamingCodexDecisionEngine,
    _emit_reasoning_summary_delta,
    _reasoning_summary_delta,
    _streaming_thread_options,
)


class _EventClient:
    def __init__(self, *events):
        self.events = list(events)

    async def next_event(self, *, timeout):
        del timeout
        return self.events.pop(0)


class _Context:
    def __init__(self, *, fail=False):
        self.events = []
        self.fail = fail

    def emit(self, event_type, title, payload):
        if self.fail:
            raise RuntimeError("presentation sink unavailable")
        self.events.append((event_type, title, dict(payload)))


class TestCodexReasoningSummary(BaseCase):
    def _settings(self, *, effort=None):
        return CodexAgentSettings(
            executable=Path("/tmp/codex"),
            codex_home=Path("/tmp/codex-home"),
            reasoning_effort=effort,
        )

    def _engine(self):
        return StreamingCodexDecisionEngine(self._settings())

    def test_streaming_adapter_requests_readable_summary_without_raw_reasoning(self):
        self.assertEqual(
            _streaming_thread_options(self._settings(effort="high")),
            {
                "config": {
                    "model_reasoning_effort": "high",
                    "model_reasoning_summary": "auto",
                }
            },
        )

    def test_summary_delta_uses_closed_provider_shape(self):
        self.assertEqual(
            _reasoning_summary_delta(
                {
                    "delta": "Comprobaré Odoo.",
                    "itemId": "reasoning-1",
                    "summaryIndex": 0,
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
                thread_id="thread-1",
                turn_id="turn-1",
            ),
            ("reasoning-1", 0, "Comprobaré Odoo."),
        )
        with self.assertRaises(CodexAgentError):
            _reasoning_summary_delta(
                {
                    "delta": "x",
                    "itemId": "reasoning-1",
                    "summaryIndex": 0,
                    "threadId": "other-thread",
                    "turnId": "turn-1",
                },
                thread_id="thread-1",
                turn_id="turn-1",
            )

    def test_readable_summary_is_public_but_raw_reasoning_is_inert(self):
        context = _Context()
        client = _EventClient(
            {
                "method": "item/reasoning/summaryTextDelta",
                "params": {
                    "delta": "Comprobaré primero los contactos.",
                    "itemId": "reasoning-1",
                    "summaryIndex": 0,
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
            },
            {
                "method": "item/reasoning/textDelta",
                "params": {
                    "delta": "private chain of thought must stay inert",
                    "itemId": "reasoning-1",
                    "contentIndex": 0,
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "error": None,
                        "items": [],
                    },
                },
            },
        )

        asyncio.run(
            self._engine()._wait_for_completion_streaming(
                client,
                thread_id="thread-1",
                turn_id="turn-1",
                deadline=10**12,
                context=context,
                timing=lambda _stage: None,
            )
        )

        self.assertEqual(len(context.events), 1)
        self.assertEqual(context.events[0][0], "reasoning.summary.delta")
        self.assertEqual(
            context.events[0][2],
            {
                "item_id": "reasoning-1",
                "summary_index": 0,
                "text": "Comprobaré primero los contactos.",
            },
        )
        self.assertNotIn("private chain of thought", repr(context.events))

    def test_reasoning_summary_sink_failure_never_fails_authoritative_turn(self):
        context = _Context(fail=True)
        self.assertFalse(
            _emit_reasoning_summary_delta(
                context,
                item_id="reasoning-1",
                summary_index=0,
                text="Readable summary",
            )
        )

    def test_second_agent_message_disables_provisional_stream_without_failing_turn(self):
        context = _Context()
        final_text = '{"decision":{"kind":"final_answer","answer":"Hecho"}}'
        client = _EventClient(
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "delta": '{"decision":{"kind":"final_answer","answer":"Preparando',
                    "itemId": "message-1",
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "delta": final_text,
                    "itemId": "message-2",
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"id": "message-2", "type": "agentMessage", "text": final_text},
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "completed",
                        "error": None,
                        "items": [],
                    },
                },
            },
        )

        completed = asyncio.run(
            self._engine()._wait_for_completion_streaming(
                client,
                thread_id="thread-1",
                turn_id="turn-1",
                deadline=10**12,
                context=context,
                timing=lambda _stage: None,
            )
        )

        self.assertEqual(completed["items"][-1]["text"], final_text)
