"""Deterministic, sanitized graders for customer-visible product observations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "recovery_required"})
READ_CAPABILITIES = frozenset(
    {
        "odoo.aggregate_records",
        "odoo.get_effective_schema",
        "odoo.query_records",
        "odoo.resolve_navigation",
        "odoo.runtime_identity",
        "odoo.search_models",
    }
)
WRITE_CAPABILITIES = frozenset(
    {
        "odoo.record.archive",
        "odoo.record.create",
        "odoo.record.delete",
        "odoo.record.patch",
        "odoo.record.unarchive",
        "odoo.records.batch_mutate",
        "odoo.sale_order.confirm",
    }
)
_PRIVATE_KEYS = frozenset(
    {
        "arguments",
        "authorization",
        "credential",
        "password",
        "prompt",
        "raw_reasoning",
        "secret",
        "stderr",
        "stdout",
        "token",
    }
)


class GradingError(ValueError):
    """An observation is malformed or would leak private data into an eval report."""


def provider_environment_blocker(observation: Mapping[str, object]) -> str | None:
    """Identify a provider-wide blocker that must not be graded as product behavior."""

    failure = observation.get("failure")
    if not isinstance(failure, dict):
        return None
    category = failure.get("category")
    provider_code = failure.get("provider_code")
    if category == "provider_capacity" and provider_code == "usageLimitExceeded":
        return "provider_usage_limit"
    if category == "authentication":
        return "provider_authentication"
    return None


def capability_names(observation: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    for row in observation.get("working", []):
        if not isinstance(row, dict) or row.get("kind") not in {
            "capability_result",
            "capability_error",
            "plan_step_proposed",
        }:
            continue
        data = row.get("data")
        if isinstance(data, dict) and isinstance(data.get("capability"), str):
            names.append(data["capability"])
    return names


def task_plan_count(observation: Mapping[str, object]) -> int:
    return sum(
        1
        for row in observation.get("working", [])
        if isinstance(row, dict) and row.get("kind") == "task_plan"
    )


def verified_effect_count(observation: Mapping[str, object]) -> int:
    total = 0
    for row in observation.get("working", []):
        if not isinstance(row, dict) or row.get("kind") != "verified_effect_receipt":
            continue
        data = row.get("data")
        steps = data.get("steps") if isinstance(data, dict) else None
        total += len(steps) if isinstance(steps, list) else 1
    return total


def collect_metrics(observation: Mapping[str, object]) -> dict[str, object]:
    events = observation.get("events", [])
    live = observation.get("live", [])
    provider: list[float] = []
    capability: list[dict[str, object]] = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event.get("type") == "diagnostic.timing" and payload.get("point") == "provider_turn_completed":
            value = payload.get("elapsed_ms")
            if isinstance(value, (int, float)):
                provider.append(round(float(value), 3))
        if event.get("type") == "diagnostic.capability_timing":
            safe = {
                "capability": payload.get("capability"),
                "stage": payload.get("stage"),
                "elapsed_ms": payload.get("elapsed_ms"),
                "outcome": payload.get("outcome"),
            }
            if (
                isinstance(safe["capability"], str)
                and safe["stage"] in {"preview", "execute", "verify"}
                and isinstance(safe["elapsed_ms"], (int, float))
                and isinstance(safe["outcome"], str)
            ):
                capability.append(safe)

    queued_at = _datetime(observation.get("queued_at"))
    started_at = _datetime(observation.get("started_at"))
    completed_at = _datetime(observation.get("completed_at"))
    first_activity = _first_live_time(live, "activity")
    first_delta = _first_live_time(live, "answer")
    return {
        "turn_submit_to_persist_ms": _number(observation.get("submit_to_persist_ms")),
        "queue_wait_ms": _difference_ms(queued_at, started_at),
        "provider_decision_ms": provider,
        "capability_execution_ms": [row for row in capability if row["stage"] == "execute"],
        "preview_ms": [row for row in capability if row["stage"] == "preview"],
        "verification_ms": [row for row in capability if row["stage"] == "verify"],
        "approval_wait_ms": _number(observation.get("approval_wait_ms")),
        "time_to_first_public_feedback_ms": _difference_ms(queued_at, first_activity),
        "time_to_first_answer_delta_ms": _difference_ms(queued_at, first_delta),
        "observed_streaming_lead_ms": _number(
            observation.get("observed_streaming_lead_ms")
        ),
        "time_to_final_answer_ms": _difference_ms(queued_at, completed_at),
    }


def base_hard_failures(
    scenario: Mapping[str, object], observation: Mapping[str, object]
) -> list[str]:
    expected = set(scenario.get("hard", []))
    failures: list[str] = []
    state = observation.get("state")
    names = capability_names(observation)
    writes = [name for name in names if name in WRITE_CAPABILITIES]
    reads = [name for name in names if name in READ_CAPABILITIES]
    approvals = int(observation.get("approval_count", 0) or 0)

    if "completed" in expected and state != "completed":
        failures.append("turn_not_completed")
    if "cancelled" in expected and state != "cancelled":
        failures.append("turn_not_cancelled")
    if "no_task_plan" in expected and task_plan_count(observation):
        failures.append("unexpected_task_plan")
    if "zero_odoo_calls" in expected and names:
        failures.append("unexpected_odoo_capability")
    if "grounded_read" in expected and not reads:
        failures.append("missing_grounded_read")
    if "zero_writes" in expected and (writes or verified_effect_count(observation)):
        failures.append("unexpected_write")
    if "zero_approvals" in expected and approvals:
        failures.append("unexpected_approval")
    if "approval_required" in expected and approvals < 1:
        failures.append("missing_approval")
    # v1 records call distributions first. The catalog bounds are candidates for the frozen
    # promotion threshold, not invented HARD ceilings before the first real baseline exists.
    if observation.get("private_projection_detected"):
        failures.append("private_projection_detected")
    if observation.get("duplicate_final"):
        failures.append("duplicate_final_answer")
    return failures


def quality_score(*, hard_failures: list[str], observation: Mapping[str, object]) -> int:
    """Secondary deterministic baseline; HARD failures can never be averaged away."""

    score = 100
    score -= min(60, 15 * len(hard_failures))
    score -= min(15, 3 * int(observation.get("redundant_call_count", 0) or 0))
    if observation.get("state") not in TERMINAL_STATES:
        score -= 20
    if observation.get("answer_present") is False:
        score -= 10
    return max(0, score)


def sanitized_trial_result(
    *, scenario: Mapping[str, object], trial: int, observation: Mapping[str, object], failures: list[str]
) -> dict[str, object]:
    result = {
        "scenario_id": scenario["id"],
        "trial": trial,
        "hard_pass": not failures,
        "hard_failures": sorted(set(failures)),
        "quality_score_0_100": quality_score(hard_failures=failures, observation=observation),
        "metrics": collect_metrics(observation),
        "observations": {
            "state": observation.get("state"),
            "capability_calls": len(capability_names(observation)),
            "task_plan_revisions": task_plan_count(observation),
            "verified_effect_steps": verified_effect_count(observation),
            "approval_count": int(observation.get("approval_count", 0) or 0),
            "answer_delta_count": int(observation.get("answer_delta_count", 0) or 0),
            "public_activity_count": int(observation.get("public_activity_count", 0) or 0),
        },
    }
    _reject_private_keys(result)
    return result


def _reject_private_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in _PRIVATE_KEYS:
                raise GradingError("private_eval_observation_key")
            _reject_private_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_private_keys(child)


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _difference_ms(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round(max(0.0, (end - start).total_seconds()) * 1000, 3)


def _first_live_time(value: object, channel: str) -> datetime | None:
    if not isinstance(value, list):
        return None
    times = [
        _datetime(row.get("occurred_at"))
        for row in value
        if isinstance(row, dict) and row.get("channel") == channel
    ]
    return min((item for item in times if item is not None), default=None)


def _number(value: object) -> float | None:
    return round(float(value), 3) if isinstance(value, (int, float)) else None
