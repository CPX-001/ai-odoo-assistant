import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_read_acceptance.py"
SPEC = importlib.util.spec_from_file_location("phase0_read_acceptance", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
phase0_read_acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase0_read_acceptance)


def _trace(events):
    return {
        "capture_kind": "live_http",
        "scenario_id": "read_partner",
        "request_error_code": None,
        "capture_error_code": None,
        "status_snapshots": [
            {"state": "queued", "events": []},
            {"state": "completed", "events": [{"type": event} for event in events]},
        ],
    }


def test_completed_apology_without_tool_evidence_is_rejected():
    result = phase0_read_acceptance.evaluate_read_capture(_trace(["reasoning.completed"]))
    assert result["accepted"] is False
    assert result["missing_tool_events"] == ["tool.completed", "tool.started"]


def test_completed_read_with_tool_cycle_is_accepted():
    result = phase0_read_acceptance.evaluate_read_capture(
        _trace(["tool.started", "tool.completed", "reasoning.completed"])
    )
    assert result["accepted"] is True
    assert result["missing_tool_events"] == []


def test_interrupted_capture_is_rejected_even_with_tool_events():
    trace = _trace(["tool.started", "tool.completed"])
    trace["capture_error_code"] = "odoo_http_unavailable"
    assert phase0_read_acceptance.evaluate_read_capture(trace)["accepted"] is False
