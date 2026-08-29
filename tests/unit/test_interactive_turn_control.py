from dataclasses import dataclass

from addons.odoo_ai_assistant.runtime.agent.interactive_codex import (
    TurnControlSnapshot,
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


def test_control_snapshot_preserves_ordered_redirects():
    snapshot = _control_snapshot(
        _Context(
            _Env(
                {
                    "cancel_requested": False,
                    "sequence": 2,
                    "applied_sequence": 1,
                    "interventions": [
                        {"sequence": 1, "message": "primera corrección"},
                        {"sequence": 2, "message": "segunda corrección"},
                    ],
                }
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
