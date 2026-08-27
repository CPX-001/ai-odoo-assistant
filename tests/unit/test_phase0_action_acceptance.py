import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_action_acceptance.py"
SPEC = importlib.util.spec_from_file_location("phase0_action_acceptance", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


def _base():
    return {
        "request_kind": "explicit_supported_write",
        "turn_state": "awaiting_confirmation",
        "plan_state": "awaiting_confirmation",
        "plan_step_count": 1,
        "preview_observed": True,
        "approval_required": True,
        "record_unchanged_before_approval": True,
        "error_code": None,
    }


def test_rejects_completed_zero_step_action_without_preview():
    value = {
        **_base(),
        "turn_state": "completed",
        "plan_state": "completed",
        "plan_step_count": 0,
        "preview_observed": False,
    }

    result = acceptance.evaluate(value)

    assert result["accepted"] is False
    assert "action_plan_missing" in result["reasons"]
    assert "approval_preview_missing" in result["reasons"]


def test_accepts_supported_write_stopped_at_required_preview():
    result = acceptance.evaluate(_base())

    assert result == {
        "format_version": 1,
        "request_kind": "explicit_supported_write",
        "accepted": True,
        "reasons": [],
        "turn_state": "awaiting_confirmation",
        "plan_state": "awaiting_confirmation",
        "plan_step_count": 1,
        "preview_observed": True,
    }


def test_rejects_preview_when_preapproval_unchanged_state_is_not_proven():
    value = {**_base(), "record_unchanged_before_approval": False}

    result = acceptance.evaluate(value)

    assert result["accepted"] is False
    assert result["reasons"] == ["preapproval_state_not_proven"]
