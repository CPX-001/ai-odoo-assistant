import json
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "e2e" / "embedded_phase0_scenarios.json"
EXPECTED_SCENARIOS = {
    "hello",
    "read_partner",
    "query_sales",
    "aggregate_sales",
    "write_preview",
    "write_execute_verify",
    "acl_denied",
    "provider_auth_missing",
    "provider_process_missing",
    "provider_disconnect",
    "provider_timeout",
    "tool_invalid_input",
    "tool_handler_failure",
    "invalid_final_output",
    "cancel_queued",
    "cancel_running",
    "worker_restart_before_write",
    "worker_loss_after_write_barrier",
}
TERMINAL_STATES = {
    "queued",
    "awaiting_confirmation",
    "completed",
    "failed",
    "cancelled",
    "recovery_required",
}


def test_phase0_scenario_catalog_is_complete_and_bounded() -> None:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert payload["format_version"] == 1
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    assert 1 <= len(scenarios) <= 32

    ids = {scenario["id"] for scenario in scenarios}
    assert ids == EXPECTED_SCENARIOS
    assert len(ids) == len(scenarios)

    for scenario in scenarios:
        assert set(scenario) == {
            "id",
            "category",
            "requires",
            "expected_terminal_states",
            "purpose",
        }
        assert isinstance(scenario["category"], str) and scenario["category"]
        assert isinstance(scenario["requires"], list)
        assert all(isinstance(item, str) and item for item in scenario["requires"])
        assert scenario["expected_terminal_states"]
        assert set(scenario["expected_terminal_states"]) <= TERMINAL_STATES
        assert isinstance(scenario["purpose"], str) and scenario["purpose"].endswith(".")
