from pathlib import Path

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def test_browser_assets_use_only_the_authenticated_odoo_bridge() -> None:
    manifest = (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    static_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADDON_ROOT / "static").rglob("*")
        if path.is_file()
    )

    assert '"web"' in manifest
    assert '"web.assets_backend"' in manifest
    assert '"web.assets_unit_tests"' in manifest
    assert 'rpcCall("/odoo_ai/v1/explain"' in static_text
    assert "orm.call(" not in static_text
    assert "fetch(" not in static_text
    assert "127.0.0.1" not in static_text
    assert "X-Odoo-AI-Shared-Secret" not in static_text
    assert "X-Odoo-AI-Delegation" not in static_text
    assert "delegation_token" not in static_text
    assert "innerHTML" not in static_text
    assert "t-raw" not in static_text
    assert "/v1/admin/source" not in static_text
    assert "/v1/admin/logs" not in static_text

    browser_controller = (ADDON_ROOT / "controllers/browser_bridge.py").read_text(encoding="utf-8")
    assert 'auth="user"' in browser_controller
    assert 'request.env["odoo.ai.assistant.bridge"]' in browser_controller
    assert "/odoo_ai/v1/context-read" in browser_controller
    assert "/odoo_ai/v1/explain" in browser_controller
    assert '"uid"' not in browser_controller


def test_internal_tool_routes_have_double_auth_and_no_generic_execution() -> None:
    controller = (ADDON_ROOT / "controllers/internal_tools.py").read_text(encoding="utf-8")

    assert "/odoo_ai/internal/v1/model-metadata" in controller
    assert "/odoo_ai/internal/v1/read-records" in controller
    assert "/odoo_ai/internal/v1/instance-inventory" in controller
    assert 'auth="none"' in controller
    assert "require_machine_secret(" in controller
    assert "DELEGATION_HEADER" in controller
    assert "DelegatedOrmToolExecutor" in controller
    assert "execute_kw" not in controller
    assert "execute_method" not in controller


def test_internal_endpoint_and_secret_are_not_duplicated_in_views() -> None:
    view_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ADDON_ROOT / "views").glob("*.xml")
    )

    assert "127.0.0.1" not in view_text
    assert "X-Odoo-AI-Shared-Secret" not in view_text
    assert "shared_secret" not in view_text
    assert "ODOO_AI_SOURCE_ROOTS" not in view_text
    assert "ODOO_AI_LOG_FILE" not in view_text
    assert "ODOO_AI_JOURNAL_UNIT" not in view_text


def test_browser_bridge_derives_server_context_and_returns_a_sanitized_shape() -> None:
    bridge = (ADDON_ROOT / "models/assistant_bridge.py").read_text(encoding="utf-8")

    assert "prepare_context_turn(" in bridge
    assert "env=self.env" in bridge
    assert "prepared.to_assistant_payload()" in bridge
    assert "prepared.delegation_token" in bridge
    assert '"uid"' not in bridge
    assert '"user"' not in bridge
    assert "_browser_explain_response" in bridge
    assert "logical_path" in bridge
    assert "raw Evidence" not in bridge


def test_m2_paths_have_no_privilege_or_generic_execution_escape_hatches() -> None:
    roots = [
        ADDON_ROOT / "controllers",
        ADDON_ROOT / "models",
        ADDON_ROOT / "services",
    ]
    source = "\n".join(
        path.read_text(encoding="utf-8") for root in roots for path in root.rglob("*.py")
    )

    assert ".sudo(" not in source
    assert "execute_kw" not in source
    assert "execute_method" not in source
    assert "env.cr.execute(" not in source
    assert "SELECT *" not in source
