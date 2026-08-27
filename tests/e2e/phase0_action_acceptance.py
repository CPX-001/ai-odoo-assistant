#!/usr/bin/env python3
"""Evaluate sanitized Phase 0 ACTION evidence without replaying a business write."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUEST_KIND = "explicit_supported_write"
_CAPABILITY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_DIAGNOSTIC_TOKEN = re.compile(r"^[a-z0-9_]{1,64}$")
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_DIAGNOSTIC_COUNT_KEYS = frozenset(
    {
        "reasoning_tool_count",
        "planning_tool_count",
        "staged_plan_count",
        "structured_plan_count",
        "final_plan_count",
    }
)
_LIFECYCLE_EVENTS = frozenset(
    {
        "reasoning.started",
        "reasoning.completed",
        "approval.required",
        "approval.approved",
        "approval.rejected",
        "execution.barrier",
        "recovery.required",
    }
)


def _safe_capability(value: Any) -> str | None:
    return value if isinstance(value, str) and _CAPABILITY.fullmatch(value) else None


def _safe_tool_sequence(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        return []
    result: list[str] = []
    for item in value:
        capability = _safe_capability(item)
        if capability is None:
            return []
        result.append(capability)
    return result


def _safe_planning_checkpoint(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    point = item.get("point")
    if not isinstance(point, str) or _DIAGNOSTIC_TOKEN.fullmatch(point) is None:
        return None
    safe: dict[str, Any] = {"point": point}
    capability = _safe_capability(item.get("capability"))
    if capability is not None:
        safe["capability"] = capability
    source = item.get("source")
    if isinstance(source, str) and _DIAGNOSTIC_TOKEN.fullmatch(source):
        safe["source"] = source
    for key in _DIAGNOSTIC_COUNT_KEYS:
        count = item.get(key)
        if type(count) is int and 0 <= count <= 32:
            safe[key] = count
    return safe


def _safe_planning_diagnostics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 32:
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        safe = _safe_planning_checkpoint(item)
        if safe is None:
            return []
        result.append(safe)
    return result


def _boundary_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 64:
        return []
    result: list[dict[str, Any]] = []
    for snapshot in value:
        if not isinstance(snapshot, dict):
            return []
        events = snapshot.get("events", [])
        if not isinstance(events, list) or len(events) > 128:
            return []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if not isinstance(event_type, str) or _EVENT_TYPE.fullmatch(event_type) is None:
                continue
            payload = event.get("payload")
            if event_type == "diagnostic.planning":
                checkpoint = _safe_planning_checkpoint(payload)
                if checkpoint is not None:
                    result.append({"type": event_type, **checkpoint})
            elif event_type.startswith("tool."):
                capability = (
                    _safe_capability(payload.get("capability"))
                    if isinstance(payload, dict)
                    else None
                )
                row: dict[str, Any] = {"type": event_type}
                if capability is not None:
                    row["capability"] = capability
                result.append(row)
            elif event_type in _LIFECYCLE_EVENTS:
                result.append({"type": event_type})
            if len(result) >= 128:
                return result
    return result


def _derived_tool_sequence(boundary_events: list[dict[str, Any]]) -> list[str]:
    return [
        capability
        for event in boundary_events
        if event.get("type") == "tool.started"
        and (capability := _safe_capability(event.get("capability"))) is not None
    ]


def _derived_planning_diagnostics(
    boundary_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for event in boundary_events:
        if event.get("type") != "diagnostic.planning":
            continue
        checkpoint = _safe_planning_checkpoint(
            {key: value for key, value in event.items() if key != "type"}
        )
        if checkpoint is not None:
            result.append(checkpoint)
    return result


def evaluate(value: dict[str, Any]) -> dict[str, Any]:
    request_kind = value.get("request_kind")
    turn_state = value.get("turn_state")
    plan_state = value.get("plan_state")
    plan_step_count = value.get("plan_step_count")
    preview_observed = value.get("preview_observed")
    approval_required = value.get("approval_required")
    record_unchanged_before_approval = value.get("record_unchanged_before_approval")
    error_code = value.get("error_code")

    reasons: list[str] = []
    if request_kind != REQUEST_KIND:
        reasons.append("request_kind_invalid")
    if error_code is not None:
        reasons.append("turn_error_present")
    if turn_state not in {"awaiting_confirmation", "completed"}:
        reasons.append("turn_state_invalid")
    if type(plan_step_count) is not int or plan_step_count < 1:
        reasons.append("action_plan_missing")
    if preview_observed is not True:
        reasons.append("approval_preview_missing")
    if approval_required is not True:
        reasons.append("approval_not_required")
    if record_unchanged_before_approval is not True:
        reasons.append("preapproval_state_not_proven")
    if plan_state not in {"awaiting_confirmation", "completed"}:
        reasons.append("plan_state_invalid")

    boundary_events = _boundary_events(value.get("status_snapshots"))
    tool_sequence = _safe_tool_sequence(value.get("tool_sequence"))
    if not tool_sequence:
        tool_sequence = _derived_tool_sequence(boundary_events)
    planning_diagnostics = _safe_planning_diagnostics(value.get("planning_diagnostics"))
    if not planning_diagnostics:
        planning_diagnostics = _derived_planning_diagnostics(boundary_events)

    return {
        "format_version": 1,
        "request_kind": request_kind,
        "accepted": not reasons,
        "reasons": reasons,
        "turn_state": turn_state,
        "plan_state": plan_state,
        "plan_step_count": plan_step_count if type(plan_step_count) is int else None,
        "preview_observed": preview_observed is True,
        "tool_sequence": tool_sequence,
        "planning_diagnostics": planning_diagnostics,
        "boundary_events": boundary_events,
    }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("action_evidence_invalid")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = evaluate(_load(args.evidence))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
