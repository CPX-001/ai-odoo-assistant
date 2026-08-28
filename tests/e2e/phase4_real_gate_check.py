from __future__ import annotations

import json
from pathlib import Path

path = Path(__file__).with_name("phase4_real_gates.json")
data = json.loads(path.read_text(encoding="utf-8"))
required = {
    "P4-REAL-FIRST-DELTA",
    "P4-REAL-FINAL-PARITY",
    "P4-REAL-CANCEL-STREAM",
    "P4-REAL-UTF8-FRAGMENT",
}
assert data.get("format_version") == 1
assert isinstance(data.get("gates"), list)
assert {gate.get("id") for gate in data["gates"]} == required
fields = {
    "id", "phase", "preconditions", "user", "data", "injection", "action",
    "backend_expected", "browser_expected", "redaction", "cleanup", "command",
}
for gate in data["gates"]:
    assert set(gate) == fields
    assert gate["phase"] == 4
    assert all(
        isinstance(gate[key], str) and gate[key]
        for key in fields - {"phase", "preconditions"}
    )
    assert isinstance(gate["preconditions"], list) and gate["preconditions"]
print("phase4 real-gate manifest: 4 definitions valid")
