"""Odoo-native M7 settings surface for bounded Assistant configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services import AssistantServiceClient, AssistantServiceError
from .assistant_bridge import (
    SECRET_FILE_ENV,
    SECRET_FILE_PARAM,
    SERVICE_URL_ENV,
    SERVICE_URL_PARAM,
    TURN_TIMEOUT_ENV,
    TURN_TIMEOUT_PARAM,
)

SYSTEM_ADMIN_GROUP = "base.group_system"
CONFIG_CLIENT_TIMEOUT_SECONDS = 15.0


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    assistant_service_url = fields.Char(
        string="Requested service URL override",
        groups=SYSTEM_ADMIN_GROUP,
        help="Optional Odoo-side override. Empty falls back to the setup-provided URL.",
    )
    assistant_service_url_effective = fields.Char(
        string="Effective service URL",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_service_url_origin = fields.Char(
        string="Service URL origin",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_machine_credential_configured = fields.Boolean(
        string="Machine credential reference configured",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
        help=(
            "Only configuration presence is exposed; the reference and credential are never shown."
        ),
    )
    assistant_source_roots = fields.Text(
        string="Requested source roots",
        groups=SYSTEM_ADMIN_GROUP,
        help=(
            "One absolute path per line. Every path is revalidated by the Assistant Service "
            "against setup-authorized roots before it can become effective."
        ),
    )
    assistant_source_authorized_roots = fields.Text(
        string="Setup-authorized source roots",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_log_provider = fields.Selection(
        selection=[
            ("auto", "Automatic"),
            ("file", "File"),
            ("journal", "systemd journal"),
        ],
        string="Requested log provider",
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_log_provider_options = fields.Char(
        string="Host-authorized log providers",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_knowledge_provider = fields.Char(
        string="Knowledge provider",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_reasoning_model = fields.Char(
        string="Requested reasoning model",
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_reasoning_startup_timeout_seconds = fields.Float(
        string="Requested startup timeout (seconds)",
        groups=SYSTEM_ADMIN_GROUP,
        help="Set to 0 to use the host/runtime value. Allowed override range: 1..120.",
    )
    assistant_reasoning_turn_timeout_seconds = fields.Float(
        string="Requested turn timeout (seconds)",
        groups=SYSTEM_ADMIN_GROUP,
        help="Set to 0 to use the host/runtime value. Allowed override range: 5..600.",
    )
    assistant_config_revision = fields.Integer(
        string="Configuration revision",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_config_fingerprint = fields.Char(
        string="Configuration fingerprint",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_config_validation_state = fields.Char(
        string="Validation state",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_config_post_action = fields.Char(
        string="Post-save action",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_config_effective_summary = fields.Text(
        string="Effective values and provenance",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )
    assistant_host_only_summary = fields.Text(
        string="Host-owned boundaries",
        readonly=True,
        groups=SYSTEM_ADMIN_GROUP,
    )

    @api.model
    def get_values(self):
        self._require_system_admin()
        values = super().get_values()
        parameters = self.env["ir.config_parameter"]
        requested_url = parameters._get_param(SERVICE_URL_PARAM) or ""
        setup_url = os.environ.get(SERVICE_URL_ENV, "")
        effective_url = requested_url or setup_url
        secret_reference = parameters._get_param(SECRET_FILE_PARAM) or os.environ.get(
            SECRET_FILE_ENV
        )

        values.update(
            {
                "assistant_service_url": requested_url,
                "assistant_service_url_effective": effective_url,
                "assistant_service_url_origin": (
                    "explicit_override"
                    if requested_url
                    else ("supervisor" if setup_url else "unknown")
                ),
                "assistant_machine_credential_configured": bool(secret_reference),
                "assistant_config_validation_state": "service_unavailable",
                "assistant_config_post_action": "none",
            }
        )
        if not effective_url:
            values["assistant_config_validation_state"] = "configuration_missing"
            return values

        try:
            snapshot = self._client_for_url(effective_url).configuration_snapshot()
            values.update(_settings_values_from_snapshot(snapshot))
        except AssistantServiceError:
            # Settings must remain open so an administrator can repair the local URL.
            values["assistant_config_validation_state"] = "service_unavailable"
        return values

    def set_values(self):
        self.ensure_one()
        self._require_system_admin()

        parameters = self.env["ir.config_parameter"]
        requested_url = (self.assistant_service_url or "").strip()
        target_url = requested_url or os.environ.get(SERVICE_URL_ENV, "")
        if not target_url:
            raise ValidationError(_("A loopback Assistant Service URL is required."))

        try:
            client = self._client_for_url(target_url)
            current = client.configuration_snapshot()
            current_revision = _snapshot_revision(current)
            current_effective_url = (
                parameters._get_param(SERVICE_URL_PARAM)
                or os.environ.get(SERVICE_URL_ENV, "")
            )
            expected_revision = (
                self.assistant_config_revision
                if target_url == current_effective_url
                else current_revision
            )
            overrides = self._requested_overrides()
            client.configuration_validate({"overrides": overrides})
        except AssistantServiceError as error:
            raise ValidationError(_configuration_error_message(error.code)) from error

        # Remote validation happens before any local intent is persisted.
        super().set_values()
        parameters.set_param(SERVICE_URL_PARAM, requested_url or False)
        try:
            client.configuration_apply(
                {
                    "expected_revision": expected_revision,
                    "overrides": overrides,
                    "actor": {
                        "odoo_uid": self.env.uid,
                        "odoo_database": self.env.cr.dbname,
                    },
                }
            )
        except AssistantServiceError as error:
            # Raising keeps the Odoo transaction from persisting a partial form save.
            raise ValidationError(_configuration_error_message(error.code)) from error

    def _requested_overrides(self):
        source_roots = _parse_lines(self.assistant_source_roots)
        startup_timeout = self.assistant_reasoning_startup_timeout_seconds or 0.0
        turn_timeout = self.assistant_reasoning_turn_timeout_seconds or 0.0
        if startup_timeout and not 1.0 <= startup_timeout <= 120.0:
            raise ValidationError(_("Startup timeout must be between 1 and 120 seconds."))
        if turn_timeout and not 5.0 <= turn_timeout <= 600.0:
            raise ValidationError(_("Turn timeout must be between 5 and 600 seconds."))
        return {
            "source_roots": source_roots or None,
            "log_provider": self.assistant_log_provider or None,
            "reasoning_model": (self.assistant_reasoning_model or "").strip() or None,
            "reasoning_startup_timeout_seconds": startup_timeout or None,
            "reasoning_turn_timeout_seconds": turn_timeout or None,
        }

    @api.model
    def _client_for_url(self, service_url):
        parameters = self.env["ir.config_parameter"]
        secret_file = parameters._get_param(SECRET_FILE_PARAM) or os.environ.get(
            SECRET_FILE_ENV
        )
        raw_timeout = parameters._get_param(TURN_TIMEOUT_PARAM) or os.environ.get(
            TURN_TIMEOUT_ENV
        )
        timeout = _config_client_timeout(raw_timeout)
        try:
            return AssistantServiceClient(
                base_url=service_url,
                shared_secret_file=secret_file,
                timeout=timeout,
            )
        except AssistantServiceError as error:
            raise AssistantServiceError("configuration_invalid") from error

    @api.model
    def _require_system_admin(self):
        if not self.env.user.has_group(SYSTEM_ADMIN_GROUP):
            raise AccessError(_("Only system administrators may manage AI Assistant settings."))


def _settings_values_from_snapshot(payload):
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise AssistantServiceError("invalid_response")
    revision = _snapshot_revision(payload)
    fingerprint = payload.get("fingerprint")
    overrides = payload.get("overrides")
    authorized = payload.get("authorized")
    snapshot = payload.get("snapshot")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or not isinstance(overrides, Mapping)
        or not isinstance(authorized, Mapping)
        or not isinstance(snapshot, Mapping)
    ):
        raise AssistantServiceError("invalid_response")

    source_roots = _string_list(overrides.get("source_roots"))
    authorized_roots = _string_list(authorized.get("source_roots"))
    log_providers = _string_list(authorized.get("log_providers"))
    values = snapshot.get("values")
    if not isinstance(values, list):
        raise AssistantServiceError("invalid_response")

    effective_lines = []
    host_lines = []
    knowledge_provider = "unknown"
    for item in values:
        if not isinstance(item, Mapping):
            raise AssistantServiceError("invalid_response")
        key = item.get("key")
        ownership = item.get("ownership")
        provenance = item.get("provenance")
        state = item.get("value_state")
        if not all(isinstance(value, str) for value in (key, ownership, provenance, state)):
            raise AssistantServiceError("invalid_response")
        if ownership == "host_only":
            reason = item.get("readonly_reason")
            suffix = f" - {reason}" if isinstance(reason, str) and reason else ""
            host_lines.append(f"{key}: {state} ({provenance}){suffix}")
        else:
            value = item.get("effective_value")
            rendered = _render_admin_value(value)
            effective_lines.append(f"{key}: {rendered} ({provenance})")
        if key == "knowledge.provider" and isinstance(item.get("effective_value"), str):
            knowledge_provider = item["effective_value"]

    return {
        "assistant_source_roots": "\n".join(source_roots),
        "assistant_source_authorized_roots": "\n".join(authorized_roots),
        "assistant_log_provider": overrides.get("log_provider") or False,
        "assistant_log_provider_options": ", ".join(log_providers) or "none",
        "assistant_knowledge_provider": knowledge_provider,
        "assistant_reasoning_model": overrides.get("reasoning_model") or False,
        "assistant_reasoning_startup_timeout_seconds": (
            overrides.get("reasoning_startup_timeout_seconds") or 0.0
        ),
        "assistant_reasoning_turn_timeout_seconds": (
            overrides.get("reasoning_turn_timeout_seconds") or 0.0
        ),
        "assistant_config_revision": revision,
        "assistant_config_fingerprint": fingerprint,
        "assistant_config_validation_state": payload.get("validation_state") or "unknown",
        "assistant_config_post_action": payload.get("post_action") or "none",
        "assistant_config_effective_summary": "\n".join(effective_lines),
        "assistant_host_only_summary": "\n".join(host_lines),
    }


def _snapshot_revision(payload):
    if not isinstance(payload, Mapping):
        raise AssistantServiceError("invalid_response")
    revision = payload.get("revision")
    if type(revision) is not int or revision < 0:
        raise AssistantServiceError("invalid_response")
    return revision


def _parse_lines(value):
    if not value:
        return []
    lines = [line.strip() for line in value.splitlines()]
    roots = [line for line in lines if line]
    if len(roots) > 32 or len(roots) != len(set(roots)):
        raise ValidationError(_("Source roots must be unique and limited to 32 entries."))
    if any(not root.startswith("/") for root in roots):
        raise ValidationError(_("Source roots must be absolute paths."))
    return roots


def _string_list(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AssistantServiceError("invalid_response")
    return value


def _render_admin_value(value):
    if value is None:
        return "empty"
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value) if value else "empty"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    raise AssistantServiceError("invalid_response")


def _config_client_timeout(value):
    if value in {None, ""}:
        return CONFIG_CLIENT_TIMEOUT_SECONDS
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return CONFIG_CLIENT_TIMEOUT_SECONDS
    if not 0 < parsed <= 300:
        return CONFIG_CLIENT_TIMEOUT_SECONDS
    return min(parsed, CONFIG_CLIENT_TIMEOUT_SECONDS)


def _configuration_error_message(code):
    messages = {
        "authentication_rejected": _("Assistant Service rejected its machine credential."),
        "authentication_unavailable": _("Assistant machine credential is unavailable on the host."),
        "authentication_unconfigured": _("Assistant machine credential is not configured."),
        "configuration_invalid": _(
            "Configuration is invalid or outside the setup-authorized boundaries."
        ),
        "configuration_revision_conflict": _(
            "Configuration changed since this Settings form was loaded. Reload and retry."
        ),
        "diagnostic_not_found": _(
            "The Assistant Service does not expose the M7 configuration API yet."
        ),
        "service_unavailable": _("Assistant Service is unavailable at the selected loopback URL."),
    }
    return messages.get(code, _("Assistant configuration could not be applied safely."))
