import asyncio
from dataclasses import dataclass

import pytest

from addons.odoo_ai_assistant.runtime.agent.codex import CodexAgentError
from addons.odoo_ai_assistant.runtime.agent.interactive_codex import (
    TurnControlSnapshot,
    _InteractiveClientProxy,
    _RedirectRequested,
    _control_snapshot,
    intervention_working_items,
)


class _TurnModel:
    def __init__(self, payload):
        self.payload = payload
        self.applied = []

    def runtime_control_snapshot(self, turn_id):
        assert turn_id == "turn-control-0001"
        return self.payload

    def mark_runtime_control_applied(self, turn_id, sequence):
        assert turn_id == "turn-control-0001"
        self.applied.append(sequence)
        return True


class _Env:
    def __init__(self, payload):
        self.model = _TurnModel(payload)

    def __getitem__(self, name):
        assert name == "odoo.ai.turn"
        return self.model


@dataclass
class _Context:
    env: object
    turn_id: str = "turn-control-0001"


@dataclass
class _Settings:
    shutdown_timeout_seconds: float = 1.0


class _Client:
    def __init__(self, responses=None):
        self.settings = _Settings()
        self.responses = dict(responses or {})
        self.requests = []

    async def request(self, method, params, *, timeout):
        self.requests.append((method, params, timeout))
        response = self.responses.get(method)
        if isinstance(response, Exception):
            raise response
        return response


def _payload(*, cancelled=False, sequence=0, applied=0, messages=()):
    return {
        "cancel_requested": cancelled,
        "sequence": sequence,
        "applied_sequence": applied,
        "interventions": [
            {"sequence": index + 1, "message": message}
            for index, message in enumerate(messages)
        ],
    }


def _proxy(payload, client, steered):
    return _InteractiveClientProxy(
        client,
        context=_Context(_Env(payload)),
        baseline_sequence=0,
        thread_id="thread-1",
        turn_id="turn-1",
        on_steered=steered.append,
    )


def test_control_snapshot_preserves_ordered_redirects():
    snapshot = _control_snapshot(
        _Context(
            _Env(
                _payload(
                    sequence=2,
                    applied=1,
                    messages=("primera corrección", "segunda corrección"),
                )
            )
        )
    )
    assert snapshot.sequence == 2
    assert snapshot.applied_sequence == 1
    assert [item["message"] for item in snapshot.interventions] == [
        "primera corrección",
        "segunda corrección",
    ]


def test_interventions_are_provider_data_not_private_transcript_mutations():
    original = (
        {
            "sequence": 1,
            "kind": "user_input",
            "data": {"message": "original"},
        },
    )
    snapshot = TurnControlSnapshot(
        sequence=1,
        applied_sequence=0,
        interventions=({"sequence": 1, "message": "corrige el periodo"},),
    )
    projected = intervention_working_items(original, snapshot)
    assert projected[0] == original[0]
    assert projected[1] == {
        "kind": "user_intervention",
        "source": "user",
        "sequence": 1,
        "message": "corrige el periodo",
    }
    assert len(original) == 1


def test_live_redirect_uses_turn_steer_with_expected_turn_id():
    steered = []
    client = _Client({"turn/steer": {"turnId": "turn-1"}})
    proxy = _proxy(
        _payload(sequence=2, messages=("primera", "segunda")),
        client,
        steered,
    )

    asyncio.run(proxy._check_control())

    assert steered == [2]
    assert [request[0] for request in client.requests] == ["turn/steer"]
    method, params, timeout = client.requests[0]
    assert method == "turn/steer"
    assert params["threadId"] == "thread-1"
    assert params["expectedTurnId"] == "turn-1"
    assert "Correction 1: primera" in params["input"][0]["text"]
    assert "Correction 2: segunda" in params["input"][0]["text"]
    assert timeout <= 0.5


def test_live_redirect_interrupts_ephemeral_subturn_when_steer_is_unavailable():
    steered = []
    client = _Client(
        {
            "turn/steer": RuntimeError("unsupported"),
            "turn/interrupt": {},
        }
    )
    proxy = _proxy(_payload(sequence=1, messages=("corrige",)), client, steered)

    with pytest.raises(_RedirectRequested):
        asyncio.run(proxy._check_control())

    assert steered == []
    assert [request[0] for request in client.requests] == ["turn/steer", "turn/interrupt"]
    assert client.requests[1][1] == {"threadId": "thread-1", "turnId": "turn-1"}


def test_stop_interrupts_only_the_bound_ephemeral_subturn():
    steered = []
    client = _Client({"turn/interrupt": {}})
    proxy = _proxy(_payload(cancelled=True), client, steered)

    with pytest.raises(CodexAgentError) as captured:
        asyncio.run(proxy._check_control())

    assert captured.value.code == "agent_cancelled"
    assert steered == []
    assert [request[0] for request in client.requests] == ["turn/interrupt"]
    assert client.requests[0][1] == {"threadId": "thread-1", "turnId": "turn-1"}
