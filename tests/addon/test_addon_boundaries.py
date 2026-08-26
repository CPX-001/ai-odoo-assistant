from pathlib import Path
from xml.etree import ElementTree

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def _static_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADDON_ROOT / "static").rglob("*")
        if path.is_file()
    )


def test_browser_assets_use_only_authenticated_odoo_routes() -> None:
    source = _static_text()
    assert 'rpcCall("/odoo_ai/v1/turn"' in source
    assert 'rpcCall("/odoo_ai/v1/turn/status"' in source
    assert "fetch(" not in source
    assert "127.0.0.1" not in source
    assert "X-Odoo-AI-Shared-Secret" not in source
    assert "X-Odoo-AI-Delegation" not in source
    assert "delegation_token" not in source
    assert "innerHTML" not in source
    assert "t-raw" not in source


def test_internal_tools_expose_only_residual_inventory_callback() -> None:
    controller = (ADDON_ROOT / "controllers/internal_tools.py").read_text(encoding="utf-8")
    assert "/odoo_ai/internal/v1/instance-inventory" in controller
    assert 'auth="none"' in controller
    assert "require_machine_secret(" in controller
    for retired in (
        "/odoo_ai/internal/v1/model-metadata",
        "/odoo_ai/internal/v1/read-records",
        "/odoo_ai/internal/v1/navigation",
        "/odoo_ai/internal/v1/query-schema",
        "/odoo_ai/internal/v1/query-records",
        "/odoo_ai/internal/v1/aggregate-records",
        "/odoo_ai/internal/v1/action-write-schema",
        "/odoo_ai/internal/v1/action-preview",
        "/odoo_ai/internal/v1/action-commit",
        "/odoo_ai/internal/v1/action-verify",
        "DELEGATION_HEADER",
        "DelegatedOrmToolExecutor",
        "ApprovedActionToolExecutor",
    ):
        assert retired not in controller
    assert "execute_kw" not in controller
    assert "execute_method" not in controller


def test_turn_controller_is_the_authenticated_browser_ingress() -> None:
    controller = (ADDON_ROOT / "controllers/turn_runtime.py").read_text(encoding="utf-8")
    for route in (
        "/odoo_ai/v1/turn",
        "/odoo_ai/v1/turn/status",
        "/odoo_ai/v1/turn/cancel",
        "/odoo_ai/v1/turn/plan-decision",
        "/odoo_ai/v1/turn/plan-status",
    ):
        assert route in controller
    assert 'auth="user"' in controller


def test_history_ui_never_replaces_the_account_gate_before_authentication() -> None:
    history = (
        ADDON_ROOT
        / "static/src/components/assistant_history/assistant_history.xml"
    ).read_text(encoding="utf-8")
    assert (
        "state.runtimeState === 'authenticated' and state.historyView" in history
    )
    assert (
        "state.runtimeState === 'authenticated' and !state.historyView" in history
    )
    auth_service = (
        ADDON_ROOT / "static/src/services/zz_assistant_auth_service.js"
    ).read_text(encoding="utf-8")
    assert "state.historyView = false;" in auth_service


def test_account_ui_polls_and_settings_target_exists_in_odoo_18() -> None:
    auth_service = (
        ADDON_ROOT / "static/src/services/zz_assistant_auth_service.js"
    ).read_text(encoding="utf-8")
    assert "const LOGIN_POLL_DELAY_MS = 5000;" in auth_service
    panel_path = (
        ADDON_ROOT / "static/src/components/assistant_panel/assistant_panel.xml"
    )
    panel = ElementTree.parse(panel_path)
    refresh_labels = [
        " ".join(button.itertext()).strip()
        for button in panel.findall(".//button[@t-on-click='refreshRuntimeAccount']")
    ]
    assert "Comprobar" not in refresh_labels
    static_source = _static_text()
    assert "base.action_res_config_settings" not in static_source
    assert "base_setup.action_general_configuration" in static_source
    panel_component = (
        ADDON_ROOT / "static/src/components/assistant_panel/assistant_panel.js"
    ).read_text(encoding="utf-8")
    assert 'this.actionService = useService("action");' in panel_component
    assert "Actualizar cuenta" not in static_source
    assert "Actualizar uso" not in static_source
    assert 'duration === 300' in static_source
    assert 'return _t("5 horas")' in static_source
    assert 'duration === 10080' in static_source
    assert 'return _t("Semanal")' in static_source
    assert "service.refreshRuntimeAccount = async () =>" in static_source
    assert "const LOGIN_POLL_DELAY_MS = 5000;" in static_source
    assert "const AUTHENTICATED_POLL_DELAY_MS = 60000;" in static_source
    assert 'globalThis.document?.visibilityState !== "hidden"' in static_source
    assert 'addEventListener?.("visibilitychange"' in static_source


def test_internal_endpoint_and_secret_are_not_duplicated_in_views() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ADDON_ROOT / "views").glob("*.xml")
    )
    assert "127.0.0.1" not in source
    assert "X-Odoo-AI-Shared-Secret" not in source
    assert "shared_secret" not in source
    assert "ODOO_AI_SOURCE_ROOTS" not in source


def test_addon_server_paths_have_no_privilege_or_generic_execution_escape_hatches() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root_name in ("controllers", "models", "services", "runtime")
        for path in (ADDON_ROOT / root_name).rglob("*.py")
    )
    assert ".sudo(" not in source
    assert "execute_kw" not in source
    assert "execute_method" not in source
    assert "env.cr.execute(" not in source
    assert "SELECT *" not in source
