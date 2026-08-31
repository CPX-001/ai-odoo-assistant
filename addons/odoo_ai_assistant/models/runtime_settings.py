"""Settings and diagnostics for the Odoo-owned Assistant runtime."""

from __future__ import annotations

from datetime import UTC, datetime

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime import (
    CodexAccountError,
    CodexAccountManager,
    CodexAccountStatus,
    RuntimePathError,
    RuntimePaths,
    detect_codex,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilitySettingType,
    discover_capabilities_for_env,
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
    assistant_codex_account_state = fields.Char(
        string="ChatGPT account state",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_account_connected = fields.Boolean(
        string="ChatGPT connected",
        readonly=True,
        groups="base.group_system",
    )
    # Upgrade bridge for databases whose stored runtime-settings view predates
    # 18.0.10.19.0.  Keep these model-only fields until that upgrade floor is retired:
    # Odoo validates the old inherited view before loading its replacement XML.
    assistant_codex_login_pending = fields.Boolean(
        string="Legacy ChatGPT login pending",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_auth_mode = fields.Char(
        string="Authentication mode",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_account_email = fields.Char(
        string="Account",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_plan_type = fields.Char(
        string="Plan",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_login_url = fields.Char(
        string="Legacy ChatGPT login page",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_login_code = fields.Char(
        string="Legacy ChatGPT device code",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_account_message = fields.Char(
        string="Account detail",
        readonly=True,
        groups="base.group_system",
    )
    assistant_codex_rate_limits = fields.Text(
        string="Codex usage",
        readonly=True,
        groups="base.group_system",
    )

    @api.model
    def get_values(self):
        self._require_capability_admin()
        values = super().get_values()
        parameters = self.env["ir.config_parameter"]
        configured = parameters._get_param("odoo_ai_assistant.codex_executable") or ""
        codex = detect_codex(configured)
        paths = None
        try:
            paths = RuntimePaths.from_odoo().ensure()
        except RuntimePathError as error:
            runtime_directory = ""
            runtime_state = str(error)
        else:
            runtime_directory = str(paths.root)
            runtime_state = "ready"

        account = CodexAccountStatus(state="runtime_unavailable")
        if codex.ready and codex.executable is not None and paths is not None:
            try:
                account = CodexAccountManager(
                    executable=codex.executable,
                    paths=paths,
                ).status(include_rate_limits=True)
            except (CodexAccountError, RuntimePathError):
                account = CodexAccountStatus(
                    state="authentication_error",
                    error_code="codex_account_unavailable",
                )

        values.update(
            {
                "assistant_codex_executable": configured,
                "assistant_codex_executable_effective": (
                    str(codex.executable) if codex.executable else ""
                ),
                "assistant_codex_state": codex.state,
                "assistant_runtime_directory": runtime_directory,
                "assistant_runtime_state": runtime_state,
                **self._account_values(account),
            }
        )
        return values

    def action_assistant_codex_account_refresh(self):
        self._require_capability_admin()
        self.ensure_one()
        return _reload_action()

    # These fail-closed shims exist only so Odoo can validate and replace a stored
    # pre-18.0.10.19.0 view during module upgrade.  The current view exposes none
    # of them and authentication remains owned by the host Codex installation.
    def action_assistant_codex_login_start(self):
        return self._retired_database_login_action()

    def action_assistant_codex_login_open(self):
        return self._retired_database_login_action()

    def action_assistant_codex_login_cancel(self):
        return self._retired_database_login_action()

    def action_assistant_codex_logout(self):
        return self._retired_database_login_action()

    @api.model
    def assistant_codex_account_status(self):
        """Bounded admin RPC for tests/future UI polling; never returns token material."""

        self._require_capability_admin()
        try:
            return self._codex_account_manager().status(include_rate_limits=True).browser_payload()
        except CodexAccountError as error:
            return CodexAccountStatus(
                state="authentication_error",
                error_code=error.code,
            ).browser_payload()

    @api.model
    def assistant_capability_catalog(self):
        """Generic settings/diagnostics surface; no per-provider fields or XML required."""

        self._require_capability_admin()
        registry = discover_capabilities_for_env(self.env)
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
        definition = discover_capabilities_for_env(self.env).resolve(capability_name)
        key = CapabilityConfigResolver.enabled_parameter_key(definition.name)
        self.env["ir.config_parameter"].set_param(key, "true" if enabled else "false")
        return True

    @api.model
    def assistant_set_capability_setting(self, capability_name, setting_key, value):
        self._require_capability_admin()
        definition = discover_capabilities_for_env(self.env).resolve(capability_name)
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

    def _retired_database_login_action(self):
        self._require_capability_admin()
        raise ValidationError(
            _("ChatGPT authentication is managed by the installation's primary Codex session.")
        )

    def _codex_account_manager(self):
        configured = (
            self.env["ir.config_parameter"]._get_param("odoo_ai_assistant.codex_executable")
            or ""
        )
        codex = detect_codex(configured)
        if not codex.ready or codex.executable is None:
            raise CodexAccountError("codex_runtime_not_found")
        try:
            paths = RuntimePaths.from_odoo().ensure()
        except RuntimePathError as error:
            raise CodexAccountError("codex_runtime_storage_unavailable") from error
        return CodexAccountManager(executable=codex.executable, paths=paths)

    @api.model
    def _account_values(self, status: CodexAccountStatus):
        return {
            "assistant_codex_account_state": self._account_state_label(status.state),
            "assistant_codex_account_connected": status.connected,
            "assistant_codex_login_pending": False,
            "assistant_codex_auth_mode": status.auth_mode or "",
            "assistant_codex_account_email": status.email or "",
            "assistant_codex_plan_type": status.plan_type or "",
            "assistant_codex_login_url": "",
            "assistant_codex_login_code": "",
            "assistant_codex_account_message": self._account_detail(status),
            "assistant_codex_rate_limits": _format_rate_limits(status.rate_limits),
        }

    @api.model
    def _account_state_label(self, state):
        return {
            "runtime_unavailable": _("Runtime unavailable"),
            "not_authenticated": _("Not connected"),
            "authenticated": _("Connected"),
            "authentication_error": _("Authentication error"),
            "login_pending": _("Login pending"),
        }.get(state, _("Unknown"))

    @api.model
    def _account_detail(self, status):
        if status.state == "login_pending":
            return _("The installation's primary Codex session is being authenticated externally.")
        if status.state == "authenticated":
            return _("Odoo is using the installation's primary Codex session.")
        if status.state == "not_authenticated":
            return _("Authenticate the installation's primary Codex CLI session outside Odoo.")
        if status.state == "runtime_unavailable":
            return _("Install or configure the Codex executable first.")
        return self._account_error_message(status.error_code or "codex_account_unavailable")

    @api.model
    def _account_error_message(self, code):
        return {
            "codex_runtime_not_found": _("The Codex executable is unavailable to the Odoo process."),
            "codex_runtime_storage_unavailable": _("The private Assistant runtime directory is unavailable."),
            "codex_account_api_unsupported": _("This Codex version does not support the required account API."),
            "codex_login_pending": _("A ChatGPT login is already in progress."),
            "codex_login_timeout": _("The ChatGPT login expired. Start a new login."),
            "codex_login_interrupted": _("The previous ChatGPT login was interrupted. Start it again."),
            "codex_login_failed": _("ChatGPT login did not complete successfully."),
            "codex_login_start_timeout": _("Codex did not initialize the login in time."),
            "codex_login_worker_failed": _("The temporary Codex login process stopped unexpectedly."),
            "codex_login_worker_start_failed": _("The temporary Codex login process could not be started."),
            "codex_initialize_response_invalid": _("This Codex version returned an incompatible App Server handshake."),
        }.get(
            code,
            _("Codex authentication could not be validated. Refresh or retry the connection."),
        )


def _format_rate_limits(rows):
    rendered = []
    for row in rows:
        limit = row.get("limit_name") or row.get("limit_id") or _("Codex limit")
        window = row.get("window") or _("window")
        used = row.get("used_percent")
        resets = row.get("resets_at")
        parts = [_("%(used)s%% used") % {"used": used}]
        if type(resets) is int:
            try:
                reset_text = datetime.fromtimestamp(resets, tz=UTC).isoformat(timespec="minutes")
            except (OverflowError, OSError, ValueError):
                reset_text = None
            if reset_text:
                parts.append(_("resets %(time)s") % {"time": reset_text})
        rendered.append(f"{limit} / {window}: " + ", ".join(parts))
    return "\n".join(rendered)


def _reload_action():
    return {"type": "ir.actions.client", "tag": "reload"}


def _setting_storage_value(value):
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        return str(value)
    raise ValidationError("Invalid capability setting")
