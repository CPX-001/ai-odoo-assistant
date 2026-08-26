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


def _provider_points():
    return {
        "submit_received": 0,
        "turn_persisted": 20,
        "worker_claimed": 40,
        "browser_first_activity": 25,
        "browser_final": 1000,
        "runtime_started": 60,
        "provider_process_started": 70,
        "provider_initialized": 100,
        "provider_thread_started": 120,
        "provider_turn_started": 140,
        "first_provider_event": 160,
        "reasoning_completed": 800,
        "result_persisted": 900,
    }


def test_phase0_report_closes_only_when_all_documented_gate_evidence_exists() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    provider = _provider_points()
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
    assert report["timing_decomposition"] == {
        "provider": True,
        "tool": True,
        "complete_turn": True,
        "scenario_ids": ["read_partner"],
    }
    assert len(report["failure_pairs"]) == 5
    assert report["failure_pair_path_count"] == 5
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


def test_phase0_report_requires_five_distinct_failure_paths() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    repeated = [
        _summary(
            "provider_auth_missing",
            final_state=None,
            error="codex_not_connected",
            ui="service_unavailable",
        )
        for _ in range(5)
    ]

    report = phase0_report.evaluate(repeated, scenarios=scenarios)

    assert len(report["failure_pairs"]) == 5
    assert report["failure_pair_path_count"] == 1
    assert report["failure_pair_scenarios"] == ["provider_auth_missing"]
    assert report["exit_gate"]["five_failure_pairs"] is False


def test_phase0_report_requires_one_turn_with_full_timing_decomposition() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    provider_only = _provider_points()
    tool_only = {
        "first_capability_started": 300,
        "last_capability_completed": 450,
        "browser_final": 900,
    }

    report = phase0_report.evaluate(
        [
            _summary("hello", timings=provider_only),
            _summary("read_partner", timings=tool_only),
        ],
        scenarios=scenarios,
    )

    assert report["timing_decomposition"]["provider"] is True
    assert report["timing_decomposition"]["tool"] is True
    assert report["timing_decomposition"]["complete_turn"] is False
    assert report["exit_gate"]["timing_decomposition"] is False


def test_phase0_report_accepts_raw_capture_and_saved_baseline_summary() -> None:
    scenarios = phase0_report._catalog(CATALOG_PATH)
    raw = {
        "format_version": 1,
        "capture_kind": "live_http",
        "expectation_met": True,
        "scenario_id": "provider_auth_missing",
        "timings": [
            {"point": "submit_received", "elapsed_ms": 0},
            {"point": "browser_final", "elapsed_ms": 9.0},
        ],
        "status_snapshots": [],
        "request_error_code": "codex_not_connected",
        "original_error_code": "codex_not_connected",
        "ui_error_code": "service_unavailable",
    }

    saved_summary = phase0_report._summary(raw, scenarios)
    loaded_summary = phase0_report._summary(saved_summary, scenarios)

    assert saved_summary["capture_kind"] == "live_http"
    assert saved_summary["expectation_met"] is True
    assert saved_summary["outcome_kind"] == "request_error"
    assert saved_summary["request_error_code"] == "codex_not_connected"
    assert loaded_summary == saved_summary
    assert phase0_report._is_live(loaded_summary) is True
