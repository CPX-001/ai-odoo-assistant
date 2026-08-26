import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "e2e" / "embedded_phase0_scenarios.json"
EXPECTED_SCENARIOS = {"hello", "read_partner", "query_sales", "aggregate_sales", "write_preview", "write_execute_verify", "acl_denied", "provider_auth_missing", "provider_process_missing", "provider_disconnect", "provider_timeout", "tool_invalid_input", "tool_handler_failure", "invalid_final_output", "cancel_queued", "cancel_running", "worker_restart_before_write", "worker_loss_after_write_barrier"}
ENTRYPOINTS = {"enqueue", "plan_decision", "cancel", "recovery"}
TERMINAL_STATES = {"queued", "awaiting_confirmation", "completed", "failed", "cancelled", "recovery_required"}
OUTCOME_KINDS = {"turn", "request_error"}


def test_phase0_scenario_catalog_is_complete_and_bounded() -> None:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert payload["format_version"] == 2
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    assert 1 <= len(scenarios) <= 32
    ids = {scenario["id"] for scenario in scenarios}
    assert ids == EXPECTED_SCENARIOS
    assert len(ids) == len(scenarios)
    for scenario in scenarios:
        assert set(scenario) == {"id", "category", "entrypoint", "requires", "expected", "purpose"}
        assert isinstance(scenario["category"], str) and scenario["category"]
        assert scenario["entrypoint"] in ENTRYPOINTS
        assert isinstance(scenario["requires"], list)
        assert all(isinstance(item, str) and item for item in scenario["requires"])
        assert isinstance(scenario["expected"], dict)
        assert set(scenario["expected"]) == {"kind", "states", "error_codes"}
        assert scenario["expected"]["kind"] in OUTCOME_KINDS
        assert set(scenario["expected"]["states"]) <= TERMINAL_STATES
        assert all(isinstance(code, str) and code for code in scenario["expected"]["error_codes"])
        if scenario["expected"]["kind"] == "turn":
            assert scenario["expected"]["states"]
        else:
            assert not scenario["expected"]["states"]
            assert scenario["expected"]["error_codes"]
        assert isinstance(scenario["purpose"], str) and scenario["purpose"].endswith(".")


def test_pre_enqueue_provider_gate_scenarios_match_current_product_contract() -> None:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    scenarios = {scenario["id"]: scenario for scenario in payload["scenarios"]}
    auth_missing = scenarios["provider_auth_missing"]
    assert auth_missing["entrypoint"] == "enqueue"
    assert auth_missing["expected"] == {"kind": "request_error", "states": [], "error_codes": ["codex_not_connected"]}
    process_missing = scenarios["provider_process_missing"]
    assert process_missing["entrypoint"] == "enqueue"
    assert process_missing["expected"] == {"kind": "request_error", "states": [], "error_codes": ["codex_unavailable"]}
