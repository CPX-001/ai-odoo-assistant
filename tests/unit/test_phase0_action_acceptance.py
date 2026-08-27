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
        "tool_sequence": [],
        "planning_diagnostics": [],
        "boundary_events": [],
    }


def test_rejects_preview_when_preapproval_unchanged_state_is_not_proven():
    value = {**_base(), "record_unchanged_before_approval": False}

    result = acceptance.evaluate(value)

    assert result["accepted"] is False
    assert result["reasons"] == ["preapproval_state_not_proven"]


def test_preserves_only_bounded_content_free_action_diagnostics():
    value = {
        **_base(),
        "tool_sequence": [
            "odoo.get_effective_schema",
            "odoo.get_effective_write_schema",
            "odoo.query_records",
        ],
        "planning_diagnostics": [
            {
                "point": "plan_step_staged",
                "capability": "odoo.record.patch",
                "staged_plan_count": 1,
                "secret": "drop-me",
            },
            {
                "point": "final_plan_reconciled",
                "structured_plan_count": 0,
                "staged_plan_count": 1,
                "final_plan_count": 1,
                "source": "staged_fallback",
                "arguments": {"phone": "drop-me"},
            },
        ],
    }

    result = acceptance.evaluate(value)

    assert result["tool_sequence"] == value["tool_sequence"]
    assert result["planning_diagnostics"] == [
        {
            "point": "plan_step_staged",
            "capability": "odoo.record.patch",
            "staged_plan_count": 1,
        },
        {
            "point": "final_plan_reconciled",
            "structured_plan_count": 0,
            "staged_plan_count": 1,
            "final_plan_count": 1,
            "source": "staged_fallback",
        },
    ]
    assert "drop-me" not in str(result)


def test_derives_boundary_log_from_diagnostic_capture_snapshots():
    value = {
        **_base(),
        "status_snapshots": [
            {
                "state": "running",
                "events": [
                    {
                        "type": "tool.started",
                        "payload": {
                            "capability": "odoo.get_effective_write_schema",
                            "secret": "drop-me",
                        },
                    },
                    {
                        "type": "tool.completed",
                        "payload": {"capability": "odoo.get_effective_write_schema"},
                    },
                    {
                        "type": "diagnostic.planning",
                        "payload": {
                            "point": "plan_step_staged",
                            "capability": "odoo.record.patch",
                            "staged_plan_count": 1,
                            "arguments": {"phone": "drop-me"},
                        },
                    },
                    {"type": "approval.required", "payload": {"plan_id": "drop-me"}},
                ],
            }
        ],
    }

    result = acceptance.evaluate(value)

    assert result["tool_sequence"] == ["odoo.get_effective_write_schema"]
    assert result["planning_diagnostics"] == [
        {
            "point": "plan_step_staged",
            "capability": "odoo.record.patch",
            "staged_plan_count": 1,
        }
    ]
    assert result["boundary_events"] == [
        {"type": "tool.started", "capability": "odoo.get_effective_write_schema"},
        {"type": "tool.completed", "capability": "odoo.get_effective_write_schema"},
        {
            "type": "diagnostic.planning",
            "point": "plan_step_staged",
            "capability": "odoo.record.patch",
            "staged_plan_count": 1,
        },
        {"type": "approval.required"},
    ]
    assert "drop-me" not in str(result)
