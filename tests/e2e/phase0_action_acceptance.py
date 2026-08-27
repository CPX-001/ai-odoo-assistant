#!/usr/bin/env python3
"""Evaluate sanitized Phase 0 ACTION evidence without replaying a business write."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUEST_KIND = "explicit_supported_write"


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

    return {
        "format_version": 1,
        "request_kind": request_kind,
        "accepted": not reasons,
        "reasons": reasons,
        "turn_state": turn_state,
        "plan_state": plan_state,
        "plan_step_count": plan_step_count if type(plan_step_count) is int else None,
        "preview_observed": preview_observed is True,
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
