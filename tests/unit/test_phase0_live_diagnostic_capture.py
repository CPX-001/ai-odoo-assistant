import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_live_diagnostic_capture.py"
SPEC = importlib.util.spec_from_file_location("phase0_live_diagnostic_capture", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
diagnostic_capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic_capture)


def test_preserves_only_validated_capability_identifier_on_tool_events():
    event = {
        "sequence": 7,
        "type": "tool.completed",
        "payload": {
            "capability": "odoo.get_effective_write_schema",
            "arguments": {"secret": "drop-me"},
            "result": "drop-me",
        },
    }

    safe = diagnostic_capture._safe_event(event)

    assert safe == {
        "sequence": 7,
        "type": "tool.completed",
        "payload": {"capability": "odoo.get_effective_write_schema"},
    }
    assert "drop-me" not in str(safe)


def test_preserves_bounded_content_free_planning_checkpoint():
    event = {
        "sequence": 8,
        "type": "diagnostic.planning",
        "payload": {
            "point": "final_plan_reconciled",
            "capability": "odoo.record.patch",
            "structured_plan_count": 0,
            "staged_plan_count": 1,
            "final_plan_count": 1,
            "source": "staged_fallback",
            "arguments": {"phone": "drop-me"},
            "answer": "drop-me",
        },
    }

    safe = diagnostic_capture._safe_event(event)

    assert safe == {
        "sequence": 8,
        "type": "diagnostic.planning",
        "payload": {
            "point": "final_plan_reconciled",
            "capability": "odoo.record.patch",
            "structured_plan_count": 0,
            "staged_plan_count": 1,
            "final_plan_count": 1,
            "source": "staged_fallback",
        },
    }
    assert "drop-me" not in str(safe)


def test_invalid_capability_identifier_is_not_preserved():
    safe = diagnostic_capture._safe_event(
        {
            "type": "tool.started",
            "payload": {"capability": "bad capability with spaces", "secret": "drop-me"},
        }
    )

    assert safe == {"type": "tool.started"}
