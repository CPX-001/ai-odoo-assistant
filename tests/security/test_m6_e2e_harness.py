from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_m6_browser_harness_covers_required_action_boundaries() -> None:
    browser = (REPO_ROOT / "tests/e2e/m6_action_browser.mjs").read_text(
        encoding="utf-8"
    )

    for evidence in (
        'selectOption("ACTION")',
        '"Aprobar y verificar"',
        ': "Cancelar"',
        'state, "stale"',
        '"approval_binding_mismatch"',
        '"proposal_already_decided"',
        '"approval_expired"',
        "globalThis.m6Pwned",
        'decisionPath = "/odoo_ai/v1/action-decision"',
        'browser_to_assistant_requests: 0',
    ):
        assert evidence in browser
    assert 'values: { reference: "M6-TAMPERED" }' in browser
    assert "delegation_token" in browser
    assert "payload_fingerprint" in browser


def test_m6_runner_is_disposable_and_fault_checks_ambiguous_commit() -> None:
    runner = (REPO_ROOT / "tests/e2e/run_m6_action_codex.py").read_text(
        encoding="utf-8"
    )

    for evidence in (
        "CREATE ROLE",
        "CREATE DATABASE",
        "DROP DATABASE IF EXISTS {} WITH (FORCE)",
        "DROP ROLE IF EXISTS",
        '"--init=odoo_ai_assistant,odoo_ai_m6_action_items"',
        '"--update=odoo_ai_assistant,odoo_ai_m6_action_items"',
        '"odoo.get_effective_write_schema"',
        '"odoo.preview_record_patch"',
        '"/odoo_ai/internal/v1/action-commit"',
        "ambiguous commit response was not dropped exactly once",
        "Assistant role unexpectedly connected to Odoo DB",
        "preview_payload = jsonb_set",
        '{"verified", "rejected", "stale", "expired"}',
        "env=common_env",
        "env=service_env",
    ):
        assert evidence in runner
    assert 'any("commit" in name or "approve" in name for name in tools)' in runner
