"""Settings integration for the database-scoped Codex connection gate."""

from odoo import _, api, models

from ..services.runtime_account import (
    database_connection_enabled,
    disable_database_connection,
    enable_database_connection,
)


class ResConfigSettingsRuntimeBinding(models.TransientModel):
    _inherit = "res.config.settings"

    @api.model
    def get_values(self):
        values = super().get_values()
        if database_connection_enabled(self.env):
            return values
        values.update(
            {
                "assistant_codex_account_state": _("Not connected to this database"),
                "assistant_codex_account_connected": False,
                "assistant_codex_login_pending": False,
                "assistant_codex_auth_mode": "",
                "assistant_codex_account_email": "",
                "assistant_codex_plan_type": "",
                "assistant_codex_login_url": "",
                "assistant_codex_login_code": "",
                "assistant_codex_account_message": _(
                    "Connect ChatGPT explicitly for this Odoo database before using the Assistant."
                ),
                "assistant_codex_rate_limits": "",
            }
        )
        return values

    def action_assistant_codex_login_start(self):
        enable_database_connection(self.env)
        return super().action_assistant_codex_login_start()

    def action_assistant_codex_login_cancel(self):
        result = super().action_assistant_codex_login_cancel()
        disable_database_connection(self.env)
        return result

    def action_assistant_codex_logout(self):
        result = super().action_assistant_codex_logout()
        disable_database_connection(self.env)
        return result
