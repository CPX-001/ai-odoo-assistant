from pathlib import Path

ADDON_ROOT = Path(__file__).parents[2] / "addons/odoo_ai_assistant"


def test_addon_has_no_browser_to_assistant_service_path() -> None:
    manifest = (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")

    assert "assets" not in manifest
    assert not (ADDON_ROOT / "static").exists()
    assert not (ADDON_ROOT / "controllers").exists()


def test_internal_endpoint_and_secret_are_not_duplicated_in_views() -> None:
    view_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ADDON_ROOT / "views").glob("*.xml")
    )

    assert "127.0.0.1" not in view_text
    assert "X-Odoo-AI-Shared-Secret" not in view_text
    assert "shared_secret" not in view_text
