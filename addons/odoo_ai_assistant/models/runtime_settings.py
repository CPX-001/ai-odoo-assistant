"""Settings and diagnostics for the Odoo-owned Assistant runtime."""

from __future__ import annotations

from odoo import api, fields, models

from ..runtime import RuntimePathError, RuntimePaths, detect_codex


class ResConfigSettingsRuntime(models.TransientModel):
    _inherit = "res.config.settings"

    assistant_codex_executable = fields.Char(
        string="Codex executable override",
        config_parameter="odoo_ai_assistant.codex_executable",
        groups="base.group_system",
        help="Optional absolute path or executable name. Empty uses PATH auto-detection.",
    )
    assistant_codex_executable_effective = fields.Char(
        string="Detected Codex executable",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_state = fields.Char(
        string="Codex state",
        readonly=True,
        groups="base.group_system",
    )
    assistant_runtime_directory = fields.Char(
        string="Assistant runtime directory",
        readonly=True,
        groups="base.group_system",
    )
    assistant_runtime_state = fields.Char(
        string="Runtime directory state",
        readonly=True,
        groups="base.group_system",
    )

    @api.model
    def get_values(self):
        values = super().get_values()
        parameters = self.env["ir.config_parameter"]
        configured = parameters._get_param("odoo_ai_assistant.codex_executable") or ""
        codex = detect_codex(configured)
        try:
            paths = RuntimePaths.from_odoo().ensure()
        except RuntimePathError as error:
            runtime_directory = ""
            runtime_state = str(error)
        else:
            runtime_directory = str(paths.root)
            runtime_state = "ready"
        values.update(
            {
                "assistant_codex_executable": configured,
                "assistant_codex_executable_effective": (
                    str(codex.executable) if codex.executable else ""
                ),
                "assistant_codex_state": codex.state,
                "assistant_runtime_directory": runtime_directory,
                "assistant_runtime_state": runtime_state,
            }
        )
        return values
