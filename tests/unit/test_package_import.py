from importlib import import_module


def test_odoo_ai_package_is_importable() -> None:
    package = import_module("odoo_ai")

    assert package.__name__ == "odoo_ai"
