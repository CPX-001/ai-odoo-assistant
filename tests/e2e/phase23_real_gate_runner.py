#!/usr/bin/env python3
"""Print/execute one prepared Phase 2/3 validation step.

The runner never writes PASS evidence. Phase 2 real gates require both the focused
Odoo regression and the real Chromium product-path observation. Phase 3 remains
blocked until Phase 2 is formally complete.
"""

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/e2e/phase23_real_gates.json"


def gate(gate_id):
    for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["gates"]:
        if item["id"] == gate_id:
            return item
    raise SystemExit(f"unknown gate: {gate_id}")


def _odoo_selector(item):
    selector = item["backend_selector"]
    if selector.startswith("odoo_ai_assistant:"):
        return f"/{selector}"
    return selector


def backend_command(item):
    db = os.environ.get("ODOO_AI_TEST_DB")
    if not db:
        raise SystemExit("ODOO_AI_TEST_DB must name a disposable database")
    cmd = [os.environ.get("ODOO_BIN", "./odoo-bin")]
    conf = os.environ.get("ODOO_CONF")
    addons = os.environ.get("ODOO_AI_ADDONS_PATH")
    if conf:
        cmd += ["-c", conf]
    cmd += ["-d", db]
    if addons:
        cmd += ["--addons-path", addons]
    return cmd + [
        "-u",
        "odoo_ai_assistant",
        "--test-enable",
        "--test-tags",
        _odoo_selector(item),
        "--stop-after-init",
        "--log-level=test",
    ]


def browser_command(item):
    if item["phase"] == 2:
        return [
            "node",
            "tests/e2e/phase2_real_failure_browser.mjs",
            "--gate",
            item["id"],
        ]
    return ["node", "tests/e2e/phase23_hoot_gate.mjs"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", required=True)
    parser.add_argument("--execute-backend", action="store_true")
    parser.add_argument("--execute-browser", action="store_true")
    args = parser.parse_args()
    item = gate(args.gate)
    backend = backend_command(item)
    browser = browser_command(item)

    print("BACKEND REGRESSION:", shlex.join(backend))
    if item["phase"] == 2:
        print("REAL BROWSER:", shlex.join(browser))
        print(
            "SUPPLEMENTAL HOOT:",
            f"ODOO_AI_HOOT_FILTER={shlex.quote(item['browser_filter'])} "
            "node tests/e2e/phase23_hoot_gate.mjs",
        )
    else:
        print(
            "BROWSER (eligible only after Phase 2 COMPLETE):",
            f"ODOO_AI_HOOT_FILTER={shlex.quote(item['browser_filter'])} "
            "node tests/e2e/phase23_hoot_gate.mjs",
        )
    print("EXPECTED:", item["backend_expected"], "/", item["browser_expected"])
    print("REDACTION:", item["redaction"])
    print("CLEANUP:", item["cleanup"])

    if args.execute_backend:
        result = subprocess.run(backend, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    if args.execute_browser:
        if item["phase"] != 2:
            raise SystemExit(
                "Phase 3 browser execution is blocked until Phase 2 is formally COMPLETE"
            )
        result = subprocess.run(browser, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
