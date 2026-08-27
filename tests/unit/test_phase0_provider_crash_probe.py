import importlib.util
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"e2e"/"phase0_provider_crash_probe.py"
S=importlib.util.spec_from_file_location("probe",P); assert S and S.loader
probe=importlib.util.module_from_spec(S); S.loader.exec_module(probe)

def test_snapshot_and_restart():
    b=probe._parse_systemctl_show("ActiveState=active\nSubState=running\nMainPID=123\nNRestarts=0\nExecMainStartTimestampMonotonic=456\n")
    assert probe._service_healthy(b)
    assert not probe._service_restarted(b,dict(b))
    assert probe._service_restarted(b,dict(b,main_pid=999))

def test_journal_is_reduced_to_counts():
    s=probe._journal_indicators("codex-code-mode-host terminated with signal 5 secret=x\nother customer=x\ntrap SIGTRAP\n")
    assert s=={"signal5_lines":2,"code_mode_failure_lines":1}
    assert "secret" not in str(s)

def test_capture_summary_redacts_payloads():
    t={"scenario_id":"read_partner","status_snapshots":[{"state":"completed","events":[{"payload":{"secret":"x"}}]}],
       "request_error_code":None,"capture_error_code":None,"original_error_code":None,"expectation_met":True,
       "answer":"private","provider_stdout":"private"}
    s=probe._capture_summary(t)
    assert s["final_state"]=="completed" and s["expectation_met"] is True
    assert "private" not in str(s) and "secret" not in str(s)
