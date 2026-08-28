from __future__ import annotations

import json
from pathlib import Path

path = Path(__file__).with_name("p5_1_real_gates.json")
data = json.loads(path.read_text(encoding="utf-8"))
required = {
    "P5.1-BROWSER-MULTICHAT",
    "P5.1-BROWSER-SETTINGS-SNAPSHOT",
    "P5.1-BROWSER-REOPEN",
}
assert data.get("format_version") == 1
assert isinstance(data.get("gates"), list)
assert {gate.get("id") for gate in data["gates"]} == required
fields = {
    "id",
    "phase",
    "preconditions",
    "user",
    "data",
    "injection",
    "action",
    "backend_expected",
    "browser_expected",
    "redaction",
    "cleanup",
    "command",
}
for gate in data["gates"]:
    assert set(gate) == fields
    assert gate["phase"] == 5
    assert all(
        isinstance(gate[key], str) and gate[key]
        for key in fields - {"phase", "preconditions"}
    )
    assert isinstance(gate["preconditions"], list) and gate["preconditions"]
    assert all(isinstance(item, str) and item for item in gate["preconditions"])
print("P5.1 real-gate manifest: 3 definitions valid")
