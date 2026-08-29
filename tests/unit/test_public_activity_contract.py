from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "addons/odoo_ai_assistant/runtime/agent/public_activity.py"
spec = importlib.util.spec_from_file_location("p3_public_activity_contract", MODULE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def event(sequence=1, **overrides):
    value = {
        "sequence": sequence,
        "turn_id": "turn-public-0001",
        "kind": "capability.started",
        "phase": "capability",
        "status": "running",
        "label": "Consultando sale.order",
        "resource": {
            "model": "sale.order",
            "record_ids": [7],
            "display_names": ["S0007"],
        },
        "capability": "odoo.query_records",
        "progress": None,
        "diagnostic_code": None,
        "occurred_at": "2026-08-28T10:00:00.000000Z",
        "activity_id": "activity:v1:0123456789abcdef0123456789abcdef",
    }
    value.update(overrides)
    return value


def test_round_trip_closed_public_event():
    assert module.public_turn_event_payload(module.parse_public_turn_event(event())) == event()


def test_private_reasoning_extra_payload_and_bad_activity_id_fail_closed():
    invalid_values = [
        event(kind="agent.thinking"),
        {**event(), "payload": {"prompt": "secret"}},
        event(label="x" * 241),
        event(activity_id="operation-42"),
        event(
            resource={
                "model": "sale.order",
                "record_ids": list(range(1, 22)),
                "display_names": [],
            }
        ),
    ]
    for value in invalid_values:
        try:
            module.parse_public_turn_event(value)
        except module.PublicTurnEventError:
            pass
        else:
            raise AssertionError("invalid public event accepted")


def test_non_correlated_public_event_remains_valid():
    parsed = module.parse_public_turn_event(event(activity_id=None))
    assert parsed.activity_id is None


def test_cursor_order_turn_binding_and_reconnect():
    parsed = module.validate_event_batch(
        [event(4), event(5, kind="capability.completed", status="completed")],
        after_sequence=3,
    )
    assert [item.sequence for item in parsed] == [4, 5]
    assert parsed[0].activity_id == parsed[1].activity_id
    assert [
        item.sequence for item in module.validate_event_batch([event(6)], after_sequence=5)
    ] == [6]

    invalid_batches = [
        [event(5), event(4)],
        [event(4), event(5, turn_id="turn-public-0002")],
    ]
    for invalid in invalid_batches:
        try:
            module.validate_event_batch(invalid, after_sequence=3)
        except module.PublicTurnEventError:
            pass
        else:
            raise AssertionError("invalid batch accepted")
