from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_late_final_ux_template_cannot_restore_raw_activity_lifecycle_dump():
    source = (
        ROOT
        / "addons/odoo_ai_assistant/static/src/components/assistant_panel/zzzz_assistant_final_ux.xml"
    ).read_text(encoding="utf-8")
    assert "state.currentActivity.label" not in source
    assert 't-esc="event.label"' not in source
    assert 't-foreach="state.activityEvents"' not in source


def test_spanish_semantic_activity_catalog_entries_are_javascript_translations():
    catalog = (
        ROOT / "addons" / "odoo_ai_assistant" / "i18n" / "es.po"
    ).read_text(encoding="utf-8")
    entries = [block for block in catalog.split("\n\n") if 'msgid ""' not in block]

    assert entries
    assert all("#. odoo-javascript" in block for block in entries)
    assert all("#: code:addons/odoo_ai_assistant/" in block for block in entries)
    assert 'msgid "Analyzing the request"\nmsgstr "Analizando la petición"' in catalog


def test_semantic_activity_interactions_keep_the_component_receiver():
    source = (
        ROOT
        / "addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_panel_activity.xml"
    ).read_text(encoding="utf-8")

    for handler in [
        "openActivityReference",
        "showMoreActivityReferences",
        "showRemainingActivityReferences",
    ]:
        assert f"() =&gt; this.{handler}" in source or f"() => this.{handler}" in source

    final_references = (
        ROOT
        / "addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_navigation_references.xml"
    ).read_text(encoding="utf-8")
    assert "() => this.openFinalReference" in final_references


FAILURE = ROOT / "addons/odoo_ai_assistant/static/src/services/assistant_failure_contract.js"
STREAM = ROOT / "addons/odoo_ai_assistant/static/src/services/assistant_stream_client.js"
PRESENTATION = (
    ROOT
    / "addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_failure_messages.js"
)


def test_browser_contract_is_closed_and_effect_aware():
    source = FAILURE.read_text(encoding="utf-8")
    for field in [
        "code",
        "category",
        "retryability",
        "effect_state",
        "user_action",
        "diagnostic_id",
        "provider_code",
        "safe_details",
    ]:
        assert f'"{field}"' in source
    assert 'failure.retryability === "safe"' in source
    assert '["none", "not_started"].includes(failure.effect_state)' in source
    assert '["partial", "unknown"].includes(failure.effect_state)' in source
    assert "SENSITIVE_DETAIL_KEY_RE" in source


def test_recovery_required_tightens_browser_retry_authority():
    source = FAILURE.read_text(encoding="utf-8")
    assert "enforceRecoveryAuthority" in source
    assert 'status?.state === "recovery_required"' in source
    recovery = source.split("function enforceRecoveryAuthority", 1)[1].split(
        "export function failureErrorFromStatus", 1
    )[0]
    assert 'retryability: "never"' in recovery
    assert 'user_action: "review"' in recovery
    assert 'effect_state: ["partial", "unknown"].includes(failure.effect_state)' in recovery


def test_stream_terminal_path_uses_structured_status_failure():
    source = STREAM.read_text(encoding="utf-8")
    assert "failureErrorFromStatus(status)" in source
    assert 'throw new Error(status.error_code || "runtime_unavailable")' not in source


def test_presentation_does_not_render_safe_details_or_raw_summary():
    source = PRESENTATION.read_text(encoding="utf-8")
    body = source.split("export function failurePresentation", 1)[1]
    assert "safe_details" not in body
    assert "safe_summary" not in body
    assert "diagnostic_id" in body
    assert "no repitas la acción a ciegas" in source.lower()
