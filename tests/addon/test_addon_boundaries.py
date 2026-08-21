from pathlib import Path

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def test_browser_assets_use_only_the_odoo_orm_bridge() -> None:
    manifest = (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    static_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADDON_ROOT / "static").rglob("*")
        if path.is_file()
    )

    assert '"web"' in manifest
    assert '"web.assets_backend"' in manifest
    assert '"web.assets_unit_tests"' in manifest
    assert 'orm.call(' in static_text
    assert '"odoo.ai.assistant.bridge"' in static_text
    assert "fetch(" not in static_text
    assert "127.0.0.1" not in static_text
    assert "X-Odoo-AI-Shared-Secret" not in static_text
    assert "X-Odoo-AI-Delegation" not in static_text
    assert "delegation_token" not in static_text


def test_internal_tool_routes_have_double_auth_and_no_generic_execution() -> None:
    controller = (
        ADDON_ROOT / "controllers/internal_tools.py"
    ).read_text(encoding="utf-8")

    assert "/odoo_ai/internal/v1/model-metadata" in controller
    assert "/odoo_ai/internal/v1/read-records" in controller
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


def test_browser_bridge_derives_server_context_and_returns_a_sanitized_shape() -> None:
    bridge = (ADDON_ROOT / "models/assistant_bridge.py").read_text(encoding="utf-8")

    assert "prepare_context_turn(" in bridge
    assert "env=self.env" in bridge
    assert "prepared.to_assistant_payload()" in bridge
    assert "prepared.delegation_token" in bridge
    assert '"uid"' not in bridge
    assert '"user"' not in bridge
