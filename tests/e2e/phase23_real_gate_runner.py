#!/usr/bin/env python3
"""Print/execute one Odoo-side gate. Never writes PASS evidence by itself."""
import argparse,json,os,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; MANIFEST=ROOT/"tests/e2e/phase23_real_gates.json"
def gate(gid):
    for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["gates"]:
        if item["id"]==gid:return item
    raise SystemExit(f"unknown gate: {gid}")
def command(item):
    db=os.environ.get("ODOO_AI_TEST_DB");
    if not db: raise SystemExit("ODOO_AI_TEST_DB must name a disposable database")
    cmd=[os.environ.get("ODOO_BIN","./odoo-bin")]; conf=os.environ.get("ODOO_CONF"); addons=os.environ.get("ODOO_AI_ADDONS_PATH")
    if conf: cmd += ["-c",conf]
    cmd += ["-d",db]
    if addons: cmd += ["--addons-path",addons]
    return cmd+["-u","odoo_ai_assistant","--test-enable","--test-tags",item["backend_selector"],"--stop-after-init","--log-level=test"]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--gate",required=True); p.add_argument("--execute-backend",action="store_true"); a=p.parse_args(); item=gate(a.gate); cmd=command(item); print("BACKEND:",shlex.join(cmd)); print("BROWSER:",f"ODOO_AI_HOOT_FILTER={shlex.quote(item['browser_filter'])} node tests/e2e/phase23_hoot_gate.mjs"); print("EXPECTED:",item["backend_expected"],"/",item["browser_expected"]); print("CLEANUP:",item["cleanup"]); return subprocess.run(cmd,cwd=ROOT,check=False).returncode if a.execute_backend else 0
if __name__=="__main__": raise SystemExit(main())
