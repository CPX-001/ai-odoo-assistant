import re
from pathlib import Path
from xml.etree import ElementTree

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def _static_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADDON_ROOT / "static").rglob("*")
        if path.is_file() and path.suffix in {".js", ".scss", ".svg", ".xml"}
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


def test_retired_internal_callback_machine_auth_and_inventory_service_are_absent() -> None:
    controllers = ADDON_ROOT / "controllers"
    security = ADDON_ROOT / "security"
    services = ADDON_ROOT / "services"

    assert not (controllers / "internal_tools.py").exists()
    assert not (security / "machine_auth.py").exists()
    assert not (services / "instance_inventory.py").exists()

    supported_python = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (controllers, security, services)
        for path in root.rglob("*.py")
    )
    assert 'auth="none"' not in supported_python
    assert "auth='none'" not in supported_python
    assert "require_machine_secret(" not in supported_python
    assert "/odoo_ai/internal/v1/instance-inventory" not in supported_python
    assert "collect_instance_inventory" not in supported_python


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
    assert "const lockChat = () => {" in auth_service
    assert "state.chatBootstrapped = false;" in auth_service
    assert "state.conversations = [];" in auth_service
    assert 'state.runtimeState !== "authenticated"' in auth_service


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


def test_admin_surfaces_live_under_a_standalone_assistant_app_menu() -> None:
    navigation = ElementTree.parse(
        ADDON_ROOT / "views/assistant_navigation_views.xml"
    ).getroot()
    root_menu = navigation.find(".//menuitem[@id='menu_odoo_ai_assistant_root']")
    assert root_menu is not None
    assert root_menu.get("parent") is None
    assert root_menu.get("web_icon") == (
        "odoo_ai_assistant,static/description/icon.png"
    )

    expected_children = {
        "views/knowledge_views.xml": "menu_odoo_ai_knowledge_source",
        "views/assistant_diagnostics_views.xml": (
            "menu_odoo_ai_assistant_diagnostics"
        ),
        "views/res_config_settings_views.xml": "menu_odoo_ai_assistant_settings",
    }
    for relative_path, menu_id in expected_children.items():
        tree = ElementTree.parse(ADDON_ROOT / relative_path)
        child = tree.find(f".//menuitem[@id='{menu_id}']")
        assert child is not None
        assert child.get("parent") == "menu_odoo_ai_assistant_root"

    manifest = (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    assert '"application": True' in manifest


def test_internal_endpoint_and_secret_are_not_duplicated_in_views() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ADDON_ROOT / "views").glob("*.xml")
    )
    assert "127.0.0.1" not in source
    assert "X-Odoo-AI-Shared-Secret" not in source
    assert "shared_secret" not in source
    assert "ODOO_AI_SOURCE_ROOTS" not in source


def test_addon_server_paths_have_no_privilege_or_generic_execution_escape_hatches() -> None:
    python_sources = {
        path.relative_to(ADDON_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for root_name in ("controllers", "models", "services", "runtime")
        for path in (ADDON_ROOT / root_name).rglob("*.py")
    }
    source = "\n".join(python_sources.values())
    assert ".sudo(" not in source
    assert "execute_kw" not in source
    assert "execute_method" not in source
    assert "SELECT *" not in source

    # Raw SQL is reserved for host-owned row locking and fixed parameterized FTS.
    # It is not a capability/provider escape hatch and must not spread elsewhere.
    sql_sources = {
        path: text for path, text in python_sources.items() if ".cr.execute(" in text
    }
    assert set(sql_sources) == {
        "models/knowledge.py",
        "models/knowledge_fts_index.py",
        "models/turn_control.py",
        "models/turn_event.py",
    }
    joined_sql = "\n".join(sql_sources.values())
    assert joined_sql.count(".cr.execute(") == 5
    assert joined_sql.count("FOR UPDATE") == 3
    assert sql_sources["models/knowledge.py"].count(".cr.execute(") == 1
    assert "SELECT c.id" in sql_sources["models/knowledge.py"]
    assert "to_tsquery('simple', %s)" in sql_sources["models/knowledge.py"]
    assert "unnest(%s::text[])" in sql_sources["models/knowledge.py"]
    assert sql_sources["models/knowledge_fts_index.py"].count(".cr.execute(") == 1
    assert "CREATE INDEX IF NOT EXISTS" in sql_sources["models/knowledge_fts_index.py"]
    assert "USING GIN" in sql_sources["models/knowledge_fts_index.py"]
    assert not re.search(
        r"\.cr\.execute\(\s*(?:[rubf]{0,2})?(?:'''|\"\"\"|'|\")\s*"
        r"(?:INSERT|UPDATE|DELETE|ALTER|DROP)\b",
        joined_sql,
        flags=re.IGNORECASE,
    )
