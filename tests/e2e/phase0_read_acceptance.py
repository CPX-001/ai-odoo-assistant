#!/usr/bin/env python3
"""Validate that a Phase 0 READ capture contains capability-backed success evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

READ_SCENARIOS = {"read_partner", "query_sales", "aggregate_sales"}
REQUIRED_TOOL_EVENTS = {"tool.started", "tool.completed"}


def evaluate_read_capture(trace: dict[str, Any]) -> dict[str, Any]:
    scenario_id = trace.get("scenario_id")
    snapshots = trace.get("status_snapshots")
    final_state = None
    event_types: set[str] = set()
    if isinstance(snapshots, list):
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            state = snapshot.get("state")
            if isinstance(state, str):
                final_state = state
            events = snapshot.get("events")
            if isinstance(events, list):
                for event in events:
                    if isinstance(event, dict) and isinstance(event.get("type"), str):
                        event_types.add(event["type"])

    missing = sorted(REQUIRED_TOOL_EVENTS - event_types)
    accepted = bool(
        scenario_id in READ_SCENARIOS
        and trace.get("capture_kind") == "live_http"
        and trace.get("request_error_code") is None
        and trace.get("capture_error_code") is None
        and final_state == "completed"
        and not missing
    )
    return {
        "format_version": 1,
        "scenario_id": scenario_id,
        "accepted": accepted,
        "final_state": final_state,
        "required_tool_events": sorted(REQUIRED_TOOL_EVENTS),
        "missing_tool_events": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    if not isinstance(trace, dict):
        raise SystemExit("Phase 0 trace must be a JSON object")
    result = evaluate_read_capture(trace)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
