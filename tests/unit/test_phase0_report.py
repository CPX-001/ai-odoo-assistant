import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_report.py"
CATALOG_PATH = Path(__file__).resolve().parents[1] / "e2e" / "embedded_phase0_scenarios.json"
SPEC = importlib.util.spec_from_file_location("phase0_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
phase0_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase0_report)


def _summary(scenario_id, *, timings=None, final_state="completed", error=None, ui=None):
    return {
        "format_version": 1,
        "capture_kind": "live_http",
        "expectation_met": True,
        "scenario_id": scenario_id,
        "outcome_kind": "request_error" if final_state is None else "turn",
        "final_state": final_state,
        "original_error_code": error,
        "ui_error_code": ui,
        "timings_ms": timings or {"browser_final": 1000},
    }


def test_phase0_report_closes_only_when_all_documented_gate_evidence_exists() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    provider = {
        "submit_received": 0,
        "turn_persisted": 20,
        "browser_first_activity": 25,
        "browser_final": 1000,
        "runtime_started": 5,
        "provider_process_started": 10,
        "provider_initialized": 100,
        "provider_thread_started": 120,
        "provider_turn_started": 140,
        "first_provider_event": 160,
        "reasoning_completed": 800,
        "result_persisted": 900,
    }
    read = {
        **provider,
        "first_capability_started": 300,
        "last_capability_completed": 450,
    }
    values = [
        _summary("hello", timings=provider),
        _summary("read_partner", timings=read),
        _summary("write_preview", final_state="awaiting_confirmation"),
    ]
    for scenario_id, error in [
        ("provider_auth_missing", "codex_not_connected"),
        ("provider_process_missing", "codex_unavailable"),
        ("provider_disconnect", "codex_process_eof"),
        ("provider_timeout", "codex_read_timeout"),
        ("invalid_final_output", "codex_answer_invalid"),
    ]:
        values.append(
            _summary(
                scenario_id,
                final_state=(
                    None
                    if scenario_id in {"provider_auth_missing", "provider_process_missing"}
                    else "failed"
                ),
                error=error,
                ui="service_unavailable",
            )
        )

    report = phase0_report.evaluate(values, scenarios=scenarios)

    assert report["minimum_matrix"] == {
        "hello": True,
        "read": True,
        "action": True,
        "failure": True,
    }
    assert report["timing_decomposition"] == {"provider": True, "tool": True}
    assert len(report["failure_pairs"]) == 5
    assert report["ready_for_phase1"] is True


def test_phase0_report_keeps_gate_open_without_observed_ui_failure_pairs() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    report = phase0_report.evaluate(
        [
            _summary(
                "provider_auth_missing",
                final_state=None,
                error="codex_not_connected",
                ui=None,
            )
        ],
        scenarios=scenarios,
    )

    assert report["exit_gate"]["five_failure_pairs"] is False
    assert report["ready_for_phase1"] is False
