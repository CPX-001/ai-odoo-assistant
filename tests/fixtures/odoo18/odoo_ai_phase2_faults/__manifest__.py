# ruff: noqa: B018 - Odoo manifests are a top-level dictionary expression.
{
    "name": "Odoo AI Phase 2 Fault Fixture",
    "summary": "Test-only deterministic failures for Phase 2 real validation",
    "version": "18.0.1.0.0",
    "depends": ["odoo_ai_assistant"],
    "data": [
        "security/ir.model.access.csv",
        "data/phase2_secret_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
