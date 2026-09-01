from __future__ import annotations

import pytest

from .grading import (
    GradingError,
    base_hard_failures,
    collect_metrics,
    provider_environment_blocker,
    sanitized_trial_result,
)


def _scenario(*hard: str):
    return {"id": "PB-TEST-001", "hard": list(hard), "bounds": {"capability_calls_max": 2}}


def test_hard_grader_keeps_safety_failures_out_of_quality_average() -> None:
    observation = {
        "state": "completed",
        "working": [
            {"kind": "plan_step_proposed", "data": {"capability": "odoo.record.patch"}},
            {"kind": "task_plan", "data": {}},
        ],
        "approval_count": 1,
    }

    failures = base_hard_failures(
        _scenario("zero_writes", "zero_approvals", "no_task_plan"), observation
    )

    assert failures == ["unexpected_task_plan", "unexpected_write", "unexpected_approval"]


def test_metrics_separate_provider_preview_execute_and_verify() -> None:
    observation = {
        "queued_at": "2026-08-31T10:00:00",
        "started_at": "2026-08-31T10:00:01",
        "completed_at": "2026-08-31T10:00:05",
        "submit_to_persist_ms": 12.5,
        "approval_wait_ms": 200,
        "events": [
            {"type": "diagnostic.timing", "payload": {"point": "provider_turn_completed", "elapsed_ms": 900}},
            {"type": "diagnostic.capability_timing", "payload": {"capability": "odoo.query_records", "stage": "execute", "elapsed_ms": 35, "outcome": "success"}},
            {"type": "diagnostic.capability_timing", "payload": {"capability": "odoo.record.patch", "stage": "preview", "elapsed_ms": 20, "outcome": "success"}},
            {"type": "diagnostic.capability_timing", "payload": {"capability": "odoo.record.patch", "stage": "verify", "elapsed_ms": 25, "outcome": "success"}},
        ],
        "live": [
            {"channel": "activity", "occurred_at": "2026-08-31T10:00:01.500"},
            {"channel": "answer", "occurred_at": "2026-08-31T10:00:03"},
        ],
    }

    metrics = collect_metrics(observation)

    assert metrics["queue_wait_ms"] == 1000
    assert metrics["provider_decision_ms"] == [900.0]
    assert metrics["capability_execution_ms"][0]["elapsed_ms"] == 35
    assert metrics["preview_ms"][0]["elapsed_ms"] == 20
    assert metrics["verification_ms"][0]["elapsed_ms"] == 25
    assert metrics["time_to_first_answer_delta_ms"] == 3000


def test_report_rejects_private_observation_keys() -> None:
    from . import grading

    with pytest.raises(GradingError, match="private_eval_observation_key"):
        grading._reject_private_keys({"safe": {"prompt": "secret"}})

    result = sanitized_trial_result(
        scenario=_scenario("completed"),
        trial=1,
        observation={"state": "completed", "working": [], "prompt": "never reported"},
        failures=[],
    )
    assert "prompt" not in repr(result)


def test_global_provider_capacity_is_blocked_instead_of_graded_as_product_failure() -> None:
    assert (
        provider_environment_blocker(
            {
                "state": "failed",
                "failure": {
                    "category": "provider_capacity",
                    "provider_code": "usageLimitExceeded",
                },
            }
        )
        == "provider_usage_limit"
    )
    assert provider_environment_blocker({"state": "completed"}) is None
