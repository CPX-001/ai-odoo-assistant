#!/usr/bin/env python3
"""Validate the P5.2 real-gate manifest without claiming runtime PASS."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/e2e/p5_2_real_gates.json"
RUNNER = ROOT / "tests/e2e/p5_2_scheduler_browser.mjs"
REQUIRED = {
    "P5-REAL-MULTICHAT",
    "P5-REAL-CONVERSATION-ORDERING",
    "P5-REAL-BACKPRESSURE",
}
REQUIRED_KEYS = {
    "id",
    "phase",
    "preconditions",
    "user",
    "data",
    "action",
    "backend_expected",
    "browser_expected",
    "cleanup",
    "command",
}


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload.get("format_version") == 1
    gates = payload.get("gates")
    assert isinstance(gates, list) and gates
    by_id = {item.get("id"): item for item in gates if isinstance(item, dict)}
    assert set(by_id) == REQUIRED
    for gate_id, gate in by_id.items():
        missing = REQUIRED_KEYS - set(gate)
        assert not missing, f"{gate_id} missing {sorted(missing)}"
        assert gate["phase"] == 5
        assert isinstance(gate["preconditions"], list) and gate["preconditions"]
        assert gate["command"].endswith(gate_id)
    assert RUNNER.is_file()
    print("P5.2 gate manifest structurally valid; runtime gates remain unexecuted.")


if __name__ == "__main__":
    main()
