#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, subprocess, time
from pathlib import Path
from typing import Any

READ_ONLY_SCENARIOS = frozenset({"hello", "read_partner"})
_SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]{1,128}$")
_SIGNAL5 = re.compile(r"(?:signal\s+5\b|\bSIGTRAP\b)", re.I)
_CODE_MODE = re.compile(r"\bcodex-code-mode-host\b", re.I)
_FAILURE = re.compile(r"(?:terminated|exited|failed|crash|signal\s+\d+|SIG[A-Z]+)", re.I)

class ProbeError(RuntimeError):
    pass

def _run_text(argv, *, timeout=10.0):
    try:
        r = subprocess.run(argv, check=True, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise ProbeError("probe_command_failed") from None
    return r.stdout

def _parse_systemctl_show(text):
    allowed={"ActiveState","SubState","MainPID","NRestarts","ExecMainStartTimestampMonotonic"}
    raw={}
    for line in text.splitlines():
        if "=" not in line: continue
        k,v=line.split("=",1)
        if k not in allowed: continue
        v=v.strip()
        if k in {"MainPID","NRestarts","ExecMainStartTimestampMonotonic"}:
            try: raw[k]=int(v or "0")
            except ValueError: raise ProbeError("systemd_snapshot_invalid") from None
        else: raw[k]=v
    if not allowed.issubset(raw): raise ProbeError("systemd_snapshot_invalid")
    return {"active_state":raw["ActiveState"],"sub_state":raw["SubState"],"main_pid":raw["MainPID"],
            "n_restarts":raw["NRestarts"],"exec_main_start_monotonic":raw["ExecMainStartTimestampMonotonic"]}

def _systemd_snapshot(unit, run_text=_run_text):
    if _SAFE_UNIT.fullmatch(unit) is None: raise ProbeError("systemd_unit_invalid")
    return _parse_systemctl_show(run_text(["systemctl","show",unit,"--property=ActiveState","--property=SubState",
        "--property=MainPID","--property=NRestarts","--property=ExecMainStartTimestampMonotonic"], timeout=10.0))

def _service_restarted(before, after):
    return any(before.get(k)!=after.get(k) for k in ("main_pid","n_restarts","exec_main_start_monotonic"))

def _service_healthy(s):
    return s.get("active_state")=="active" and s.get("sub_state")=="running" and isinstance(s.get("main_pid"),int) and s["main_pid"]>0

def _journal_indicators(text):
    s5=cm=0
    for line in text.splitlines():
        s5 += bool(_SIGNAL5.search(line))
        cm += bool(_CODE_MODE.search(line) and _FAILURE.search(line))
    return {"signal5_lines":int(s5),"code_mode_failure_lines":int(cm)}

def _journal_summary(unit, since_epoch, until_epoch, run_text=_run_text):
    try:
        text=run_text(["journalctl","--unit",unit,"--since",f"@{since_epoch:.3f}","--until",f"@{until_epoch:.3f}",
                       "--no-pager","--output=cat"],timeout=15.0)
    except ProbeError:
        return {"available":False,"signal5_lines":None,"code_mode_failure_lines":None}
    return {"available":True,**_journal_indicators(text)}

def _capture_summary(trace: dict[str,Any]):
    final=None
    for snap in trace.get("status_snapshots",[]) if isinstance(trace.get("status_snapshots"),list) else []:
        if isinstance(snap,dict) and isinstance(snap.get("state"),str): final=snap["state"]
    def code(k): return trace.get(k) if isinstance(trace.get(k),str) else None
    return {"scenario_id":trace.get("scenario_id"),"final_state":final,"request_error_code":code("request_error_code"),
            "capture_error_code":code("capture_error_code"),"original_error_code":code("original_error_code"),
            "expectation_met":trace.get("expectation_met") is True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--scenario",choices=sorted(READ_ONLY_SCENARIOS),default="hello")
    ap.add_argument("--attempts",type=int,default=3)
    ap.add_argument("--systemd-unit",default="odoo.service")
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--timeout-seconds",type=float,default=180.0)
    ap.add_argument("--poll-interval-ms",type=int,default=500)
    a=ap.parse_args()
    if not 1<=a.attempts<=5: raise SystemExit("--attempts must be between 1 and 5")
    if _SAFE_UNIT.fullmatch(a.systemd_unit) is None: raise SystemExit("--systemd-unit is invalid")
    from phase0_live_capture import CaptureError,OdooJsonClient,_catalog,_screen_input,capture_enqueue_scenario
    db,login,password,message=(os.environ.get(k) for k in ("ODOO_AI_PHASE0_DB","ODOO_AI_PHASE0_LOGIN","ODOO_AI_PHASE0_PASSWORD","ODOO_AI_PHASE0_MESSAGE"))
    if not all((db,login,password,message)): raise SystemExit("Set Phase 0 Odoo credentials/message environment variables")
    scenario=_catalog(Path(__file__).with_name("embedded_phase0_scenarios.json")).get(a.scenario)
    if not isinstance(scenario,dict) or scenario.get("category")!="read_only": raise SystemExit("read-only scenario required")
    try:
        client=OdooJsonClient(os.environ.get("ODOO_AI_PHASE0_BASE_URL","http://127.0.0.1:8069"))
        client.authenticate(db=db,login=login,password=password)
    except CaptureError as e: raise SystemExit(f"Phase 0 setup failed: {e}") from None
    rows=[]
    for i in range(1,a.attempts+1):
        before=_systemd_snapshot(a.systemd_unit); started=time.time()
        trace=capture_enqueue_scenario(client=client,scenario=scenario,message=message,
            screen=_screen_input(os.environ.get("ODOO_AI_PHASE0_SCREEN_JSON")),
            timeout_seconds=a.timeout_seconds,poll_interval_seconds=max(1,a.poll_interval_ms)/1000)
        finished=time.time(); after=_systemd_snapshot(a.systemd_unit)
        rows.append({"attempt":i,"capture":_capture_summary(trace),"service_before":before,"service_after":after,
                     "service_healthy_after":_service_healthy(after),"service_restarted":_service_restarted(before,after),
                     "journal":_journal_summary(a.systemd_unit,started,finished)})
    result={"format_version":1,"probe_kind":"phase0_provider_crash_read_only","scenario_id":a.scenario,
            "attempt_count":len(rows),"attempts":rows,
            "odoo_restart_observed":any(r["service_restarted"] for r in rows),
            "odoo_unhealthy_observed":any(not r["service_healthy_after"] for r in rows),
            "provider_signal5_observed":any(isinstance(r["journal"].get("signal5_lines"),int) and r["journal"]["signal5_lines"]>0 for r in rows)}
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:result[k] for k in ("attempt_count","odoo_restart_observed","odoo_unhealthy_observed","provider_signal5_observed")},sort_keys=True))
    return 2 if result["odoo_restart_observed"] or result["odoo_unhealthy_observed"] else 0
if __name__=="__main__": raise SystemExit(main())
