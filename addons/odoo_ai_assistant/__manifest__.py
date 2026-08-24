# ruff: noqa: B018 - Odoo manifests are a top-level dictionary expression.
{
    "name": "Odoo AI Assistant",
    "summary": "Context-aware local AI assistant for Odoo",
    "version": "18.0.8.3.2",
    "category": "Administration",
    "license": "LGPL-3",
    "depends": ["account", "base", "sale", "web"],
    "data": [
        "security/user_preferences_security.xml",
        "security/ir.model.access.csv",
        "views/assistant_diagnostics_views.xml",
        "views/assistant_maintenance_views.xml",
        "views/res_config_settings_views.xml",
        "views/chat_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "odoo_ai_assistant/static/src/services/*.js",
            "odoo_ai_assistant/static/src/components/**/*.js",
            "odoo_ai_assistant/static/src/components/**/*.xml",
            "odoo_ai_assistant/static/src/components/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "odoo_ai_assistant/static/tests/**/*.test.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
