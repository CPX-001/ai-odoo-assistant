import importlib.util
import json
import subprocess
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
MODULE_PATH = FIXTURE_DIR / "phase0_codex_fault_app_server.py"
SPEC = importlib.util.spec_from_file_location("phase0_codex_fault_app_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


def _request(request_id: int, method: str, params=None) -> dict[str, object]:
    return {"id": request_id, "method": method, "params": params or {}}


def test_account_gate_is_authenticated_without_credentials_or_echo() -> None:
    request = _request(2, "account/read", {"refreshToken": False, "secret": "must-not-echo"})
    frames = fixture.handle_request("eof", request)

    assert frames == (
        {
            "id": 2,
            "result": {
                "requiresOpenaiAuth": True,
                "account": {"type": "chatgpt", "email": None, "planType": "phase0"},
            },
        },
    )
    assert "must-not-echo" not in json.dumps(frames)


def test_eof_mode_returns_turn_id_then_closes() -> None:
    frames = fixture.handle_request("eof", _request(3, "turn/start"))

    assert frames == (
        {"id": 3, "result": {"turn": {"id": "phase0-turn"}, "threadId": "phase0-thread"}},
    )


def test_timeout_mode_stalls_reasoning_initialize_but_not_account_initialize() -> None:
    account = _request(
        1,
        "initialize",
        {"clientInfo": {"name": "odoo-ai-assistant-auth"}},
    )
    reasoning = _request(
        1,
        "initialize",
        {"clientInfo": {"name": "odoo-ai-assistant"}},
    )

    assert fixture.handle_request("timeout", account)[0]["result"]["userAgent"] == (
        "odoo-ai-phase0-fault-fixture"
    )
    assert fixture.handle_request("timeout", reasoning) == ()


def test_invalid_output_mode_finishes_with_malformed_answer_only() -> None:
    frames = fixture.handle_request("invalid_output", _request(3, "turn/start"))

    assert frames[0]["id"] == 3
    assert frames[1]["method"] == "item/completed"
    assert frames[1]["params"]["item"]["text"] == "not-json"
    assert frames[2]["method"] == "turn/completed"
    assert "arguments" not in json.dumps(frames)
    assert "tool" not in json.dumps(frames)


def test_wrapper_version_and_eof_protocol() -> None:
    wrapper = FIXTURE_DIR / "codex_phase0_eof"
    version = subprocess.run(
        [sys.executable, str(wrapper), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert version.stdout.strip() == "codex-cli 0.0.0-phase0-fixture"

    payload = "\n".join(
        json.dumps(row)
        for row in (
            _request(1, "initialize"),
            {"method": "initialized"},
            _request(2, "account/read"),
            _request(3, "thread/start"),
            _request(4, "turn/start"),
        )
    ) + "\n"
    result = subprocess.run(
        [sys.executable, str(wrapper), "app-server", "--stdio"],
        input=payload,
        check=True,
        capture_output=True,
        text=True,
    )
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    assert [frame.get("id") for frame in frames] == [1, 2, 3, 4]
    assert frames[-1]["result"]["turn"]["id"] == "phase0-turn"


def test_fault_manifest_is_bounded_and_matches_fixture_files() -> None:
    manifest_path = FIXTURE_DIR / "phase0_provider_fault_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["format_version"] == 1
    cases = payload["cases"]
    assert [case["scenario_id"] for case in cases] == [
        "provider_disconnect",
        "provider_timeout",
        "invalid_final_output",
    ]
    assert {case["expected_original_error_code"] for case in cases} == {
        "codex_process_eof",
        "codex_read_timeout",
        "codex_answer_invalid",
    }
    for case in cases:
        fixture_path = Path(__file__).resolve().parents[2] / case["fixture"]
        assert fixture_path.is_file()
        assert case["expected_final_state"] == "failed"
