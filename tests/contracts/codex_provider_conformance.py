"""Adapter-neutral Codex provider conformance contract for the stabilized host loop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol

REQUIRED_CASE_IDS = frozenset({
    "initialize", "thread_isolation", "turn_output_schema", "agent_message_delta",
    "completed_agent_message", "reasoning_decision_mapping", "plan_decision_mapping",
    "final_answer_mapping", "unknown_notification", "malformed_critical_event",
    "identity_mismatch", "cancellation", "terminal_failure", "overload_backpressure",
})
VALID_OUTCOMES = frozenset({"accepted", "rejected", "cancelled", "retryable"})


class ConformanceAdapter(Protocol):
    async def observe(self, case: dict[str, Any]) -> dict[str, Any]:
        """Return a sanitized observation for one synthetic conformance case."""


def load_contract(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("format_version") != 2:
        raise ValueError("conformance_contract_invalid")
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise ValueError("conformance_contract_invalid")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("conformance_contract_invalid")
        case_id = case.get("id")
        outcome = case.get("expected_outcome")
        assertions = case.get("required_assertions")
        if (
            not isinstance(case_id, str)
            or case_id in seen
            or outcome not in VALID_OUTCOMES
            or not isinstance(assertions, list)
            or not assertions
            or any(not isinstance(item, str) or not item for item in assertions)
        ):
            raise ValueError("conformance_contract_invalid")
        seen.add(case_id)
        normalized.append({
            "id": case_id,
            "expected_outcome": outcome,
            "required_assertions": tuple(assertions),
        })
    if seen != REQUIRED_CASE_IDS:
        raise ValueError("conformance_contract_incomplete")
    return normalized


def evaluate(case: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, dict):
        return {"case_id": case["id"], "passed": False, "reason": "observation_invalid"}
    actual = observation.get("outcome")
    checks = observation.get("assertions")
    if actual not in VALID_OUTCOMES or not isinstance(checks, dict):
        return {"case_id": case["id"], "passed": False, "reason": "observation_invalid"}
    missing = [
        name
        for name in case["required_assertions"]
        if checks.get(name) is not True
    ]
    passed = actual == case["expected_outcome"] and not missing
    return {
        "case_id": case["id"],
        "passed": passed,
        "expected_outcome": case["expected_outcome"],
        "actual_outcome": actual,
        "missing_assertions": missing,
    }


async def run_suite(adapter: ConformanceAdapter, cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        observation = await adapter.observe(case)
        results.append(evaluate(case, observation))
    return {
        "format_version": 2,
        "case_count": len(results),
        "passed": all(row["passed"] for row in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()
    cases = load_contract(args.contract)
    print(json.dumps({"case_count": len(cases), "case_ids": [c["id"] for c in cases]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
