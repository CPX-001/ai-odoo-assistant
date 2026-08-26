"""Odoo-native policy settings for the embedded Assistant runtime."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

SYSTEM_ADMIN_GROUP = "base.group_system"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    assistant_agent_confirmation_mode = fields.Selection(
        selection=[
            ("always_confirm", "Always confirm"),
            ("risk_based", "Risk based"),
            ("protected_only", "Protected only"),
        ],
        string="Maximum agent autonomy",
        default="protected_only",
        config_parameter="odoo_ai_assistant.agent_confirmation_mode",
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_agent_max_auto_risk = fields.Selection(
        selection=[("low", "Low"), ("moderate", "Moderate"), ("high", "High")],
        string="Maximum automatically executed risk",
        default="high",
        config_parameter="odoo_ai_assistant.agent_max_auto_risk",
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_agent_allow_synthetic_data = fields.Boolean(
        string="Allow explicitly requested test data",
        default=True,
        config_parameter="odoo_ai_assistant.agent_allow_synthetic_data",
        groups=SYSTEM_ADMIN_GROUP,
    )

    @api.model
    def get_values(self):
        self._require_system_admin()
        return super().get_values()

    def set_values(self):
        self.ensure_one()
        self._require_system_admin()
        return super().set_values()

    @api.model
    def _require_system_admin(self):
        if not self.env.user.has_group(SYSTEM_ADMIN_GROUP):
            raise AccessError(_("Only system administrators may manage AI Assistant settings."))
