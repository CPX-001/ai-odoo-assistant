#!/usr/bin/env python3
"""Summarize one embedded Assistant Phase 0 trace without storing prompt/tool content.

The trace is intentionally transport-light. A browser/E2E runner can wrap ``fetchCall`` to retain
status envelopes and pass ``onTiming`` to ``streamAssistantChat`` for client monotonic timings.
This script combines those client timings with persisted turn-event timestamps and reports which
Foundation Stabilization Phase 0 checkpoints are still missing.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_POINTS = (
    "submit_received",
    "turn_persisted",
    "worker_claimed",
    "runtime_started",
    "provider_process_started",
    "provider_initialized",
    "provider_thread_started",
    "provider_turn_started",
    "first_provider_event",
    "first_answer_delta",
    "first_capability_started",
    "last_capability_completed",
    "reasoning_completed",
    "result_persisted",
    "browser_first_activity",
    "browser_first_answer_delta",
    "browser_final",
)

SERVER_EVENT_POINTS = {
    "queued": "turn_persisted",
    "started": "worker_claimed",
    # Current runtime emits reasoning.started immediately before AgentTurnService. Until a dedicated
    # runtime checkpoint exists this is the best persisted proxy and is labelled as such below.
    "reasoning.started": "runtime_started",
    "reasoning.completed": "reasoning_completed",
}
TERMINAL_EVENT_TYPES = {
    "approval.required",
    "completed",
    "failed",
    "cancelled",
    "recovery_required",
}


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trace_root_invalid")
    return payload


def _catalog_ids(path: Path) -> set[str]:
    payload = _load(path)
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("scenario_catalog_invalid")
    ids = {
        item.get("id")
        for item in scenarios
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(ids) != len(scenarios):
        raise ValueError("scenario_catalog_invalid")
    return ids


def _events(trace: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots = trace.get("status_snapshots", [])
    if not isinstance(snapshots, list):
        raise ValueError("status_snapshots_invalid")
    by_sequence: dict[int, dict[str, Any]] = {}
    without_sequence: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise ValueError("status_snapshot_invalid")
        rows = snapshot.get("events", [])
        if not isinstance(rows, list):
            raise ValueError("status_events_invalid")
        for event in rows:
            if not isinstance(event, dict):
                raise ValueError("status_event_invalid")
            sequence = event.get("sequence")
            if isinstance(sequence, int) and sequence >= 0:
                by_sequence.setdefault(sequence, event)
            else:
                without_sequence.append(event)
    ordered = [by_sequence[key] for key in sorted(by_sequence)]
    ordered.extend(without_sequence)
    return ordered


def _client_points(trace: dict[str, Any]) -> dict[str, float]:
    rows = trace.get("timings", [])
    if not isinstance(rows, list):
        raise ValueError("timings_invalid")
    points: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("timing_invalid")
        point = row.get("point")
        elapsed = row.get("elapsed_ms")
        if not isinstance(point, str) or not isinstance(elapsed, (int, float)):
            raise ValueError("timing_invalid")
        points.setdefault(point, round(float(elapsed), 3))
    return points


def _server_points(events: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, str]]:
    timestamps: dict[str, datetime] = {}
    provenance: dict[str, str] = {}
    last_capability: datetime | None = None
    first_event_time: datetime | None = None

    for event in events:
        event_type = event.get("type")
        occurred_at = _parse_utc(event.get("occurred_at"))
        if occurred_at is None or not isinstance(event_type, str):
            continue
        first_event_time = first_event_time or occurred_at

        mapped = SERVER_EVENT_POINTS.get(event_type)
        if mapped is not None and mapped not in timestamps:
            timestamps[mapped] = occurred_at
            provenance[mapped] = f"event:{event_type}"

        if event_type == "tool.started" and "first_capability_started" not in timestamps:
            timestamps["first_capability_started"] = occurred_at
            provenance["first_capability_started"] = "event:tool.started"
        if event_type in {"tool.completed", "tool.failed"}:
            last_capability = occurred_at
        if event_type in TERMINAL_EVENT_TYPES and "result_persisted" not in timestamps:
            timestamps["result_persisted"] = occurred_at
            provenance["result_persisted"] = f"event:{event_type}"

        if event_type == "diagnostic.timing":
            payload = event.get("payload")
            if isinstance(payload, dict):
                point = payload.get("point")
                elapsed = payload.get("elapsed_ms")
                if isinstance(point, str) and isinstance(elapsed, (int, float)):
                    # Dedicated monotonic backend checkpoints take precedence over timestamp proxies.
                    provenance[point] = "event:diagnostic.timing"

    if last_capability is not None:
        timestamps["last_capability_completed"] = last_capability
        provenance["last_capability_completed"] = "event:last tool.completed/tool.failed"

    if first_event_time is None:
        return {}, provenance
    baseline = timestamps.get("turn_persisted", first_event_time)
    elapsed = {
        point: round((timestamp - baseline).total_seconds() * 1000, 3)
        for point, timestamp in timestamps.items()
    }

    # Preserve explicit backend monotonic values when the trace contains them.
    for event in events:
        if event.get("type") != "diagnostic.timing":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        point = payload.get("point")
        value = payload.get("elapsed_ms")
        if isinstance(point, str) and isinstance(value, (int, float)):
            elapsed[point] = round(float(value), 3)
    return elapsed, provenance


def summarize(trace: dict[str, Any], *, catalog_ids: set[str]) -> dict[str, Any]:
    scenario_id = trace.get("scenario_id")
    if not isinstance(scenario_id, str) or scenario_id not in catalog_ids:
        raise ValueError("scenario_id_invalid")

    events = _events(trace)
    client = _client_points(trace)
    server, server_provenance = _server_points(events)
    points = {**server, **client}

    snapshots = trace.get("status_snapshots", [])
    final_state = None
    final_error = None
    if snapshots:
        last = snapshots[-1]
        if isinstance(last, dict):
            final_state = last.get("state") if isinstance(last.get("state"), str) else None
            final_error = (
                last.get("error_code") if isinstance(last.get("error_code"), str) else None
            )

    missing = [point for point in REQUIRED_POINTS if point not in points]
    return {
        "format_version": 1,
        "scenario_id": scenario_id,
        "final_state": final_state,
        "normalized_error_code": final_error,
        "original_error_code": trace.get("original_error_code"),
        "ui_error_code": trace.get("ui_error_code"),
        "timings_ms": {point: points[point] for point in REQUIRED_POINTS if point in points},
        "timing_provenance": {
            point: server_provenance[point]
            for point in REQUIRED_POINTS
            if point in server_provenance
        },
        "missing_checkpoints": missing,
        "model_turns": trace.get("model_turns"),
        "tool_calls": trace.get("tool_calls"),
        "token_usage": trace.get("token_usage"),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSON trace captured by the embedded E2E runner")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("embedded_phase0_scenarios.json"),
        help="Phase 0 scenario catalog",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    summary = summarize(_load(args.trace), catalog_ids=_catalog_ids(args.catalog))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
