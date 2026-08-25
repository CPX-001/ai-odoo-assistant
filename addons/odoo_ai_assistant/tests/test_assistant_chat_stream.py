import json
from unittest import TestCase
from uuid import UUID

from ..models.assistant_chat_stream import PreparedBrowserChatStream
from ..services import AssistantServiceError

TURN_ID = UUID("12345678-1234-4678-9234-567812345678")
CONVERSATION_ID = "22345678-1234-4678-9234-567812345678"


def _plan(state="completed"):
    return {
        "plan_id": "32345678-1234-4678-9234-567812345678",
        "state": state,
        "risk": "low",
        "metadata": {
            "needs_read": True,
            "needs_schema": True,
            "needs_write": False,
            "needs_business_action": False,
            "has_external_effect": False,
            "has_irreversible_effect": False,
            "is_atomic": True,
            "estimated_blast_radius": 0,
        },
        "policy": {
            "confirmation_mode": "risk_based",
            "max_auto_risk": "low",
            "allow_synthetic_data": False,
            "constrained_by": ["system_ceiling"],
        },
        "goal": "Responder" if state != "failed" else "Explicar el fallo",
        "assumptions": [],
        "steps": [],
        "requires_confirmation": False,
        "expires_at": None,
    }


def _service_response(answer="Respuesta final"):
    return {
        "status": "ok",
        "turn_id": str(TURN_ID),
        "conversation_id": None,
        "state": "completed",
        "answer_markdown": answer,
        "confidence": "high",
        "plan": _plan(),
        "completed_at": "2026-08-25T16:00:00Z",
    }


class _StreamingClient:
    def __init__(self, events):
        self.events = events
        self.append_calls = []

    def agent_turn_stream(self, payload):
        del payload
        yield from self.events

    def chat_append(self, payload):
        self.append_calls.append(payload)
        return {"conversation_id": CONVERSATION_ID}


class _BrokenClient(_StreamingClient):
    def agent_turn_stream(self, payload):
        del payload
        yield "delta", {"type": "delta", "text": "Texto provisional"}
        raise AssistantServiceError("service_unavailable")


def _prepared(client):
    failure_plan = _plan("failed")
    failure_plan["metadata"] = {
        **failure_plan["metadata"],
        "needs_read": False,
        "needs_schema": False,
    }
    return PreparedBrowserChatStream(
        client=client,
        payload={"turn_id": str(TURN_ID)},
        turn_id=TURN_ID,
        actor={"database": "customer-db", "uid": 17},
        message="Lista presupuestos",
        conversation_id=None,
        failure_plan=failure_plan,
    )


def _events(iterator):
    raw = b"".join(iterator).decode("utf-8")
    parsed = []
    for frame in raw.strip().split("\n\n"):
        lines = frame.splitlines()
        parsed.append((lines[0][7:], json.loads(lines[1][6:])))
    return raw, parsed


class TestAssistantChatStream(TestCase):
    def test_relay_forwards_visible_delta_then_validated_final(self):
        client = _StreamingClient(
            [
                ("delta", {"type": "delta", "text": "Respuesta "}),
                ("delta", {"type": "delta", "text": "final"}),
                (
                    "final",
                    {"type": "final", "response": _service_response("Respuesta final")},
                ),
            ]
        )

        raw, events = _events(_prepared(client).iter_sse())

        self.assertEqual([name for name, _ in events], ["delta", "delta", "final"])
        self.assertEqual(events[0][1], {"type": "delta", "text": "Respuesta "})
        final = events[-1][1]["response"]
        self.assertTrue(final["ok"])
        self.assertEqual(final["answer"], "Respuesta final")
        self.assertEqual(final["conversation_id"], CONVERSATION_ID)
        self.assertNotIn("event: error", raw)
        self.assertEqual(len(client.append_calls), 1)
        self.assertEqual(client.append_calls[0]["internal_workflow"], "AGENT")

    def test_broken_inner_stream_finishes_with_conversational_failed_final(self):
        client = _BrokenClient([])

        raw, events = _events(_prepared(client).iter_sse())

        self.assertEqual([name for name, _ in events], ["delta", "final"])
        final = events[-1][1]["response"]
        self.assertTrue(final["ok"])
        self.assertEqual(final["plan"]["state"], "failed")
        self.assertEqual(final["confidence"], "low")
        self.assertNotIn("service_unavailable", raw)
        self.assertNotIn("event: error", raw)
        self.assertEqual(len(client.append_calls), 1)
        self.assertEqual(client.append_calls[0]["internal_workflow"], "AGENT_FAILURE")

    def test_inner_eof_without_final_still_emits_one_failed_final(self):
        client = _StreamingClient(
            [("delta", {"type": "delta", "text": "Texto provisional"})]
        )

        raw, events = _events(_prepared(client).iter_sse())

        self.assertEqual([name for name, _ in events], ["delta", "final"])
        self.assertEqual(events[-1][1]["response"]["plan"]["state"], "failed")
        self.assertNotIn("invalid_response", raw)
        self.assertNotIn("event: error", raw)

    def test_invalid_final_is_fail_closed_and_replaced_by_failed_final(self):
        client = _StreamingClient(
            [
                (
                    "final",
                    {
                        "type": "final",
                        "response": {"status": "ok", "turn_id": str(TURN_ID)},
                    },
                )
            ]
        )

        raw, events = _events(_prepared(client).iter_sse())

        self.assertEqual([name for name, _ in events], ["final"])
        final = events[0][1]["response"]
        self.assertEqual(final["plan"]["state"], "failed")
        self.assertNotIn("invalid_response", raw)
