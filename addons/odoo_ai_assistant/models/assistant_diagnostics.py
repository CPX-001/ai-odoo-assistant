"""Administrator-only diagnostics shell for the embedded Odoo runtime."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class AssistantDiagnostics(models.TransientModel):
    _name = "odoo.ai.assistant.diagnostics"
    _description = "Odoo AI Assistant Diagnostics"

    readiness = fields.Char(readonly=True)
    diagnostic_errors = fields.Text(readonly=True)
    diagnostic_warnings = fields.Text(readonly=True)
    diagnostic_ok = fields.Text(readonly=True)

    @api.model
    def default_get(self, field_names):
        self._require_admin()
        values = super().default_get(field_names)
        values.update(self._diagnostic_values())
        return values

    def action_refresh(self):
        self._require_admin()
        self.ensure_one()
        self.write(self._diagnostic_values())
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_open_settings(self):
        self._require_admin()
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "base_setup.action_general_configuration"
        )
        action["context"] = {"module": "odoo_ai_assistant"}
        return action

    @api.model
    def _diagnostic_values(self):
        self._require_admin()
        return {
            "readiness": _("Embedded runtime"),
            "diagnostic_errors": False,
            "diagnostic_warnings": False,
            "diagnostic_ok": _("The Assistant runtime is hosted inside this Odoo process."),
        }

    @api.model
    def _require_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only system administrators can run diagnostics."))

    @api.model
    def _reasoning_setup_message(self, detail):
        del detail
        return _("Configure Codex from Settings → AI Assistant → Embedded runtime.")
