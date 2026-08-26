#!/usr/bin/env python3
"""Aggregate live Phase 0 traces/summaries and evaluate the documented exit gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

PROVIDER_POINTS = {
    "runtime_started",
    "provider_process_started",
    "provider_initialized",
    "provider_thread_started",
    "provider_turn_started",
    "first_provider_event",
}
CLIENT_POINTS = {"submit_received", "turn_persisted", "browser_first_activity", "browser_final"}
QUEUE_POINTS = {"worker_claimed"}
TOOL_POINTS = {"first_capability_started", "last_capability_completed"}
FINALIZATION_POINTS = {"reasoning_completed", "result_persisted"}
FULL_TURN_POINTS = PROVIDER_POINTS | CLIENT_POINTS | QUEUE_POINTS | TOOL_POINTS | FINALIZATION_POINTS
SIMPLE_ATTRIBUTION_POINTS = (
    PROVIDER_POINTS
    | QUEUE_POINTS
    | FINALIZATION_POINTS
    | {"submit_received", "turn_persisted", "browser_final"}
)
FAILURE_CATEGORIES = {"authorization_failure", "provider_failure", "capability_failure"}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("summary_invalid")
    return value


def _load_baseline_module():
    module_path = Path(__file__).with_name("phase0_baseline.py")
    spec = importlib.util.spec_from_file_location("phase0_baseline_report_dependency", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("phase0_baseline_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalog(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load(path)
    if payload.get("format_version") != 2 or not isinstance(payload.get("scenarios"), list):
        raise ValueError("scenario_catalog_invalid")
    scenarios: dict[str, dict[str, Any]] = {}
    for item in payload["scenarios"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("scenario_catalog_invalid")
        scenarios[item["id"]] = item
    return scenarios


def _summary(value: dict[str, Any], scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if isinstance(value.get("timings_ms"), dict):
        return value
    baseline = _load_baseline_module()
    return baseline.summarize(value, catalog_ids=set(scenarios))


def _valid_summary(summary: dict[str, Any], scenarios: dict[str, dict[str, Any]]) -> bool:
    return (
        summary.get("format_version") == 1
        and summary.get("scenario_id") in scenarios
        and isinstance(summary.get("timings_ms"), dict)
    )


def _is_live(summary: dict[str, Any]) -> bool:
    return summary.get("capture_kind") == "live_http" and summary.get("expectation_met") is True


def _has_points(summary: dict[str, Any], required: set[str]) -> bool:
    timings = summary.get("timings_ms")
    return isinstance(timings, dict) and required <= set(timings)


def _successful_turn(summary: dict[str, Any]) -> bool:
    return summary.get("outcome_kind") == "turn" and summary.get("final_state") in {
        "completed",
        "awaiting_confirmation",
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _latency_distribution(
    summaries: list[dict[str, Any]],
    scenario_ids: set[str],
) -> dict[str, Any]:
    values = [
        float(summary["timings_ms"]["browser_final"])
        for summary in summaries
        if summary.get("scenario_id") in scenario_ids
        and _is_live(summary)
        and isinstance(summary.get("timings_ms"), dict)
        and isinstance(summary["timings_ms"].get("browser_final"), (int, float))
    ]
    return {
        "samples": len(values),
        "p50_ms": _percentile(values, 0.5),
        "p95_ms": _percentile(values, 0.95),
        "min_ms": round(min(values), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
    }


def evaluate(
    values: list[dict[str, Any]],
    *,
    scenarios: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summaries = [_summary(value, scenarios) for value in values]
    if not all(_valid_summary(item, scenarios) for item in summaries):
        raise ValueError("summary_invalid")

    live = [item for item in summaries if _is_live(item)]
    live_ids = {item["scenario_id"] for item in live}
    read_ids = {
        scenario_id
        for scenario_id, scenario in scenarios.items()
        if scenario.get("category") == "read_only" and scenario_id != "hello"
    }
    write_ids = {
        scenario_id
        for scenario_id, scenario in scenarios.items()
        if scenario.get("category") == "write"
    }
    failure_ids = {
        scenario_id
        for scenario_id, scenario in scenarios.items()
        if scenario.get("category") in FAILURE_CATEGORIES
    }

    minimum_matrix = {
        "hello": "hello" in live_ids,
        "read": bool(live_ids & read_ids),
        "action": bool(live_ids & write_ids),
        "failure": bool(live_ids & failure_ids),
    }

    provider_decomposed = any(
        _successful_turn(item)
        and _has_points(item, PROVIDER_POINTS | CLIENT_POINTS | QUEUE_POINTS | FINALIZATION_POINTS)
        for item in live
    )
    tool_decomposed = any(
        _successful_turn(item)
        and item.get("scenario_id") in (read_ids | write_ids)
        and _has_points(item, TOOL_POINTS)
        for item in live
    )
    fully_decomposed = [
        item
        for item in live
        if _successful_turn(item)
        and item.get("scenario_id") in (read_ids | write_ids)
        and _has_points(item, FULL_TURN_POINTS)
    ]

    simple_ids = {"hello"} | read_ids
    simple_attributed = any(
        _successful_turn(item)
        and item.get("scenario_id") in simple_ids
        and _has_points(item, SIMPLE_ATTRIBUTION_POINTS)
        for item in live
    )

    failure_pairs = [
        {
            "scenario_id": item["scenario_id"],
            "original_error_code": item.get("original_error_code"),
            "ui_error_code": item.get("ui_error_code"),
        }
        for item in live
        if item.get("scenario_id") in failure_ids
        and isinstance(item.get("original_error_code"), str)
        and isinstance(item.get("ui_error_code"), str)
    ]
    failure_pair_scenarios = sorted({item["scenario_id"] for item in failure_pairs})

    gate = {
        "minimum_live_matrix": all(minimum_matrix.values()),
        "timing_decomposition": bool(fully_decomposed),
        "simple_latency_attributed": simple_attributed,
        "five_failure_pairs": len(failure_pair_scenarios) >= 5,
    }
    return {
        "format_version": 1,
        "live_capture_count": len(live),
        "scenario_count": len(summaries),
        "minimum_matrix": minimum_matrix,
        "timing_decomposition": {
            "provider": provider_decomposed,
            "tool": tool_decomposed,
            "complete_turn": bool(fully_decomposed),
            "scenario_ids": sorted({item["scenario_id"] for item in fully_decomposed}),
        },
        "latency": {
            "hello": _latency_distribution(live, {"hello"}),
            "simple_read": _latency_distribution(live, read_ids),
        },
        "failure_pairs": failure_pairs,
        "failure_pair_path_count": len(failure_pair_scenarios),
        "failure_pair_scenarios": failure_pair_scenarios,
        "exit_gate": gate,
        "ready_for_phase1": all(gate.values()),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("embedded_phase0_scenarios.json"),
    )
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    result = evaluate([_load(path) for path in args.captures], scenarios=_catalog(args.catalog))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["ready_for_phase1"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
