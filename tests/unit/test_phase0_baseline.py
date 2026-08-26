import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_baseline.py"
SPEC = importlib.util.spec_from_file_location("phase0_baseline", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
phase0_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase0_baseline)


def test_phase0_baseline_combines_client_and_persisted_event_timings() -> None:
    trace = {
        "capture_kind": "live_http",
        "expectation_met": True,
        "scenario_id": "hello",
        "timings": [
            {"point": "submit_received", "elapsed_ms": 0},
            {"point": "turn_persisted", "elapsed_ms": 20},
            {"point": "browser_first_activity", "elapsed_ms": 21},
            {"point": "browser_final", "elapsed_ms": 1200},
        ],
        "status_snapshots": [
            {
                "state": "queued",
                "events": [
                    {
                        "sequence": 1,
                        "type": "queued",
                        "occurred_at": "2026-08-26T20:00:00.000000Z",
                    }
                ],
            },
            {
                "state": "completed",
                "error_code": None,
                "events": [
                    {
                        "sequence": 2,
                        "type": "started",
                        "occurred_at": "2026-08-26T20:00:00.100000Z",
                    },
                    {
                        "sequence": 3,
                        "type": "reasoning.started",
                        "occurred_at": "2026-08-26T20:00:00.200000Z",
                    },
                    {
                        "sequence": 4,
                        "type": "tool.started",
                        "occurred_at": "2026-08-26T20:00:00.500000Z",
                    },
                    {
                        "sequence": 5,
                        "type": "tool.completed",
                        "occurred_at": "2026-08-26T20:00:00.700000Z",
                    },
                    {
                        "sequence": 6,
                        "type": "reasoning.completed",
                        "occurred_at": "2026-08-26T20:00:01.000000Z",
                    },
                    {
                        "sequence": 7,
                        "type": "completed",
                        "occurred_at": "2026-08-26T20:00:01.100000Z",
                    },
                ],
            },
        ],
        "request_error_code": None,
        "original_error_code": None,
        "ui_error_code": None,
        "model_turns": 1,
        "tool_calls": 1,
        "token_usage": {"input": 100, "output": 20},
    }

    summary = phase0_baseline.summarize(trace, catalog_ids={"hello"})

    assert summary["capture_kind"] == "live_http"
    assert summary["expectation_met"] is True
    assert summary["outcome_kind"] == "turn"
    assert summary["request_error_code"] is None
    assert summary["final_state"] == "completed"
    assert summary["timings_ms"]["submit_received"] == 0
    assert summary["timings_ms"]["turn_persisted"] == 20
    assert summary["timings_ms"]["worker_claimed"] == 120
    assert summary["timings_ms"]["runtime_started"] == 220
    assert summary["timings_ms"]["first_capability_started"] == 520
    assert summary["timings_ms"]["last_capability_completed"] == 720
    assert summary["timings_ms"]["reasoning_completed"] == 1020
    assert summary["timings_ms"]["result_persisted"] == 1120
    assert summary["timings_ms"]["browser_final"] == 1200
    assert summary["timing_provenance"]["turn_persisted"] == "client:onTiming"
    assert "provider_initialized" in summary["missing_checkpoints"]
    assert "browser_first_answer_delta" in summary["missing_checkpoints"]


def test_phase0_backend_monotonic_event_keeps_wall_and_runtime_domains_separate() -> None:
    trace = {
        "scenario_id": "hello",
        "timings": [],
        "status_snapshots": [
            {
                "state": "completed",
                "events": [
                    {
                        "sequence": 1,
                        "type": "queued",
                        "occurred_at": "2026-08-26T20:00:00.000000Z",
                    },
                    {
                        "sequence": 2,
                        "type": "diagnostic.timing",
                        "occurred_at": "2026-08-26T20:00:00.300000Z",
                        "payload": {"point": "provider_initialized", "elapsed_ms": 155.5},
                    },
                ],
            }
        ],
    }

    summary = phase0_baseline.summarize(trace, catalog_ids={"hello"})

    assert summary["timings_ms"]["provider_initialized"] == 300
    assert summary["runtime_monotonic_ms"]["provider_initialized"] == 155.5
    assert summary["timing_provenance"]["provider_initialized"] == "event:diagnostic.timing"


def test_phase0_baseline_preserves_pre_enqueue_request_error_metadata() -> None:
    trace = {
        "capture_kind": "live_http",
        "expectation_met": True,
        "scenario_id": "provider_auth_missing",
        "timings": [
            {"point": "submit_received", "elapsed_ms": 0},
            {"point": "browser_final", "elapsed_ms": 11.5},
        ],
        "status_snapshots": [],
        "request_error_code": "codex_not_connected",
        "original_error_code": "codex_not_connected",
        "ui_error_code": "service_unavailable",
    }

    summary = phase0_baseline.summarize(trace, catalog_ids={"provider_auth_missing"})

    assert summary["capture_kind"] == "live_http"
    assert summary["expectation_met"] is True
    assert summary["outcome_kind"] == "request_error"
    assert summary["final_state"] is None
    assert summary["request_error_code"] == "codex_not_connected"
    assert summary["normalized_error_code"] == "codex_not_connected"
    assert summary["original_error_code"] == "codex_not_connected"
    assert summary["ui_error_code"] == "service_unavailable"
    assert summary["timings_ms"] == {"submit_received": 0.0, "browser_final": 11.5}
