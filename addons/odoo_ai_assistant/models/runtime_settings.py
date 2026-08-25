"""Settings and diagnostics for the Odoo-owned Assistant runtime."""

from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime import RuntimePathError, RuntimePaths, detect_codex
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilitySettingType,
    discover_capabilities,
)


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

    @api.model
    def assistant_capability_catalog(self):
        """Generic settings/diagnostics surface; no per-provider fields or XML required."""

        self._require_capability_admin()
        registry = discover_capabilities()
        resolver = CapabilityConfigResolver.from_env(self.env)
        enabled = resolver.enablement_overrides(registry.definitions)
        context = CapabilityContext(
            env=self.env,
            turn_id="settings-catalog",
            metadata={"capability_enabled": enabled},
        )
        rows = []
        for definition, row in zip(
            registry.definitions,
            registry.catalog(context),
            strict=True,
        ):
            item = dict(row)
            item["enabled"] = enabled[definition.name]
            settings = []
            try:
                resolved = resolver.resolve(definition)
                state = "ready" if item["available"] else "unavailable"
            except CapabilityError:
                resolved = {}
                state = "missing_configuration"
            for setting in definition.settings:
                value = resolved.get(setting.key)
                settings.append(
                    {
                        "key": setting.key,
                        "title": setting.title,
                        "kind": setting.kind.value,
                        "help": setting.help,
                        "required": setting.required,
                        "choices": list(setting.choices),
                        "value": None if setting.kind is CapabilitySettingType.SECRET else value,
                        "configured": bool(value not in (None, "")),
                    }
                )
            item["state"] = state
            item["settings_schema"] = settings
            rows.append(item)
        return rows

    @api.model
    def assistant_set_capability_enabled(self, capability_name, enabled):
        self._require_capability_admin()
        if type(enabled) is not bool:
            raise ValidationError("Invalid capability enablement")
        definition = discover_capabilities().resolve(capability_name)
        key = CapabilityConfigResolver.enabled_parameter_key(definition.name)
        self.env["ir.config_parameter"].set_param(key, "true" if enabled else "false")
        return True

    @api.model
    def assistant_set_capability_setting(self, capability_name, setting_key, value):
        self._require_capability_admin()
        definition = discover_capabilities().resolve(capability_name)
        setting = next((item for item in definition.settings if item.key == setting_key), None)
        if setting is None:
            raise ValidationError("Unknown capability setting")
        resolver = CapabilityConfigResolver()
        try:
            resolver.resolve(definition, turn_overrides={setting.key: value})
        except CapabilityError as error:
            raise ValidationError("Invalid capability setting") from error
        key = CapabilityConfigResolver.parameter_key(definition.name, setting.key)
        self.env["ir.config_parameter"].set_param(key, _setting_storage_value(value))
        return True

    def _require_capability_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError("Assistant capability settings require Settings access")


def _setting_storage_value(value):
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        return str(value)
    raise ValidationError("Invalid capability setting")
