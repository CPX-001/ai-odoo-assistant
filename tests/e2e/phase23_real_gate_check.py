#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; MANIFEST=ROOT/"tests/e2e/phase23_real_gates.json"; EXPECTED={"P2-REAL-AUTH","P2-REAL-ACL","P2-REAL-TIMEOUT","P2-REAL-TOOLFAIL","P2-REAL-RECOVERY","P3-REAL-ACTIVITY-READ","P3-REAL-ACTIVITY-ACTION","P3-REAL-LIVE-VISIBILITY","P3-REAL-REDACTION"}; REQUIRED={"id","phase","preconditions","user","data","injection","action","backend_expected","browser_expected","redaction","cleanup","backend_selector","browser_filter"}
def main():
    payload=json.loads(MANIFEST.read_text(encoding="utf-8")); assert payload.get("format_version")==1; gates=payload.get("gates"); assert isinstance(gates,list) and len(gates)==9; assert {x.get("id") for x in gates}==EXPECTED
    for gate in gates:
        assert set(gate)==REQUIRED and gate["phase"] in {2,3} and isinstance(gate["preconditions"],list) and gate["preconditions"]
        for key in REQUIRED-{"phase","preconditions"}: assert isinstance(gate[key],str) and gate[key].strip()
    print("phase23 real-gate manifest: 9 definitions valid"); return 0
if __name__=="__main__": raise SystemExit(main())
