import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "e2e" / "phase0_live_capture.py"
SPEC = importlib.util.spec_from_file_location("phase0_live_capture", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
phase0_live_capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase0_live_capture)


class _FakeClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def call(self, path, params):
        self.calls.append((path, params))
        return self.results.pop(0)


class _Clock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def _turn_scenario():
    return {
        "id": "hello",
        "entrypoint": "enqueue",
        "expected": {"kind": "turn", "states": ["completed"], "error_codes": []},
    }


def test_live_capture_sanitizes_status_content_and_records_timing() -> None:
    client = _FakeClient(
        [
            {
                "ok": True,
                "turn_id": "turn-1",
                "state": "queued",
                "last_sequence": 1,
                "events": [
                    {
                        "sequence": 1,
                        "type": "queued",
                        "title": "Petición en cola",
                        "payload": {"secret": "drop-me"},
                        "occurred_at": "2026-08-26T20:00:00Z",
                    }
                ],
                "answer": "must not be retained",
                "response": {"answer": "must not be retained"},
            },
            {
                "ok": True,
                "turn_id": "turn-1",
                "state": "completed",
                "last_sequence": 4,
                "error_code": None,
                "events": [
                    {
                        "sequence": 2,
                        "type": "diagnostic.timing",
                        "title": "Provider timing checkpoint",
                        "payload": {
                            "point": "provider_initialized",
                            "elapsed_ms": 12.3456,
                            "provider_text": "drop-me",
                        },
                        "occurred_at": "2026-08-26T20:00:00.100000Z",
                    },
                    {
                        "sequence": 3,
                        "type": "reasoning.completed",
                        "payload": {"confidence": "high", "record_name": "drop-me"},
                        "occurred_at": "2026-08-26T20:00:00.200000Z",
                    },
                ],
                "response": {"ok": True, "answer": "secret business answer"},
            },
        ]
    )
    clock = _Clock([10.0, 10.02, 10.03, 10.05])

    trace = phase0_live_capture.capture_enqueue_scenario(
        client=client,
        scenario=_turn_scenario(),
        message="hello",
        screen={"model": None},
        monotonic=clock,
        sleep=lambda _: None,
    )

    assert trace["capture_kind"] == "live_http"
    assert trace["expectation_met"] is True
    assert trace["request_error_code"] is None
    assert [row["point"] for row in trace["timings"]] == [
        "submit_received",
        "turn_persisted",
        "browser_first_activity",
        "browser_final",
    ]
    rendered = str(trace)
    assert "must not be retained" not in rendered
    assert "secret business answer" not in rendered
    assert "drop-me" not in rendered
    diagnostic = trace["status_snapshots"][1]["events"][0]
    assert diagnostic["payload"] == {
        "point": "provider_initialized",
        "elapsed_ms": 12.346,
    }


def test_live_capture_records_pre_enqueue_gate_error_without_fabricating_turn() -> None:
    scenario = {
        "id": "provider_auth_missing",
        "entrypoint": "enqueue",
        "expected": {
            "kind": "request_error",
            "states": [],
            "error_codes": ["codex_not_connected"],
        },
    }
    client = _FakeClient([{"ok": False, "error": {"code": "codex_not_connected"}}])
    clock = _Clock([2.0, 2.01])

    trace = phase0_live_capture.capture_enqueue_scenario(
        client=client,
        scenario=scenario,
        message="hello",
        screen={"model": None},
        monotonic=clock,
        sleep=lambda _: None,
    )

    assert trace["expectation_met"] is True
    assert trace["status_snapshots"] == []
    assert trace["request_error_code"] == "codex_not_connected"
    assert trace["original_error_code"] == "codex_not_connected"
    assert trace["ui_error_code"] is None
    assert [row["point"] for row in trace["timings"]] == [
        "submit_received",
        "browser_final",
    ]


def test_remote_plain_http_is_refused_for_credentials() -> None:
    with pytest.raises(phase0_live_capture.CaptureError, match="insecure_remote_http_forbidden"):
        phase0_live_capture.OdooJsonClient("http://example.com:8069")
