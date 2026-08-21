from pathlib import Path

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def test_addon_has_no_browser_to_assistant_service_path() -> None:
    manifest = (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")

    assert "assets" not in manifest
    assert not (ADDON_ROOT / "static").exists()


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
