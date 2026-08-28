from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
FAILURE = ROOT / "addons/odoo_ai_assistant/static/src/services/assistant_failure_contract.js"
STREAM = ROOT / "addons/odoo_ai_assistant/static/src/services/assistant_stream_client.js"
PRESENTATION = ROOT / "addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_failure_messages.js"
def test_browser_contract_is_closed_and_effect_aware():
    source = FAILURE.read_text(encoding="utf-8")
    for field in ["code", "category", "retryability", "effect_state", "user_action", "diagnostic_id", "provider_code", "safe_details"]: assert f'"{field}"' in source
    assert 'failure.retryability === "safe"' in source
    assert '["none", "not_started"].includes(failure.effect_state)' in source
    assert '["partial", "unknown"].includes(failure.effect_state)' in source
    assert "SENSITIVE_DETAIL_KEY_RE" in source
def test_stream_terminal_path_uses_structured_status_failure():
    source = STREAM.read_text(encoding="utf-8")
    assert "failureErrorFromStatus(status)" in source
    assert 'throw new Error(status.error_code || "runtime_unavailable")' not in source
def test_presentation_does_not_render_safe_details_or_raw_summary():
    source = PRESENTATION.read_text(encoding="utf-8"); body = source.split("export function failurePresentation", 1)[1]
    assert "safe_details" not in body and "safe_summary" not in body
    assert "diagnostic_id" in body
    assert "no repitas la acción a ciegas" in source.lower()
