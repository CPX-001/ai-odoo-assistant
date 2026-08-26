"""Administrator-only Odoo view of residual Assistant Service health."""

import os
from datetime import UTC, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..services import AssistantServiceClient, AssistantServiceError

SERVICE_URL_PARAM = "odoo_ai_assistant.service_url"
SECRET_FILE_PARAM = "odoo_ai_assistant.shared_secret_file"
SERVICE_URL_ENV = "ODOO_AI_SERVICE_URL"
SECRET_FILE_ENV = "ODOO_AI_SHARED_SECRET_FILE"

_DIAGNOSTIC_KEYS = {
    "service.endpoint": "Assistant Service endpoint",
    "service.machine_auth": "Machine authentication",
    "assistant.database": "Assistant database",
    "assistant.migrations": "Database migrations",
    "assistant.configuration": "Runtime configuration",
    "instance.profile": "Odoo instance profile",
    "source.index": "Source index",
    "source.scan": "Latest source scan",
    "logs.provider": "Log provider",
    "knowledge.index": "Knowledge index",
    "reasoning.codex": "Codex runtime",
}

# Odoo deliberately re-derives trusted presentation from reason codes. Backend
# summary/remediation strings are never rendered directly.
_DIAGNOSTIC_REASON_PRESENTATION = {
    "service_reachable": ("ok", "none", "Assistant Service endpoint is reachable."),
    "machine_auth_validated": ("ok", "none", "Machine authentication is valid."),
    "database_available": ("ok", "none", "Assistant PostgreSQL storage is available."),
    "database_unavailable": (
        "error",
        "setup_required",
        "Assistant PostgreSQL storage is unavailable.",
    ),
    "migrations_at_head": ("ok", "none", "Database migrations are at the expected revision."),
    "migrations_revision_mismatch": (
        "error",
        "setup_required",
        "Database migration revision does not match this service version.",
    ),
    "configuration_valid": ("ok", "none", "Effective runtime configuration is valid."),
    "configuration_invalid": (
        "error",
        "settings",
        "Effective runtime configuration is invalid against current host boundaries.",
    ),
    "instance_available": ("ok", "none", "An authenticated Odoo instance profile is available."),
    "instance_unknown": ("degraded", "retry", "No current Odoo instance profile is available."),
    "source_operational": ("ok", "none", "Source index capability is operational."),
    "source_not_found": (
        "degraded",
        "settings",
        "No usable source tree was found inside the authorized roots.",
    ),
    "source_no_permission": (
        "error",
        "setup_required",
        "The Assistant cannot read the configured source roots.",
    ),
    "source_error": ("error", "rescan", "Source indexing reported an operational error."),
    "source_unknown": (
        "degraded",
        "rescan",
        "Source capability has not been established yet.",
    ),
    "source_scan_succeeded": ("ok", "none", "The latest source scan completed successfully."),
    "source_scan_running": ("degraded", "retry", "A source scan is currently in progress."),
    "source_scan_failed": ("error", "rescan", "The latest source scan failed."),
    "source_scan_unknown": (
        "degraded",
        "rescan",
        "No completed source scan is available yet.",
    ),
    "logs_operational": ("ok", "none", "The selected log provider is operational."),
    "logs_not_found": (
        "degraded",
        "settings",
        "No authorized log source is currently available.",
    ),
    "logs_no_permission": (
        "error",
        "setup_required",
        "The Assistant cannot read the authorized log source.",
    ),
    "logs_error": ("error", "retry", "The selected log provider reported an error."),
    "logs_unknown": ("degraded", "retry", "Log capability has not been established yet."),
    "knowledge_index_available": (
        "ok",
        "none",
        "The knowledge index contains current documents.",
    ),
    "knowledge_index_empty": (
        "degraded",
        "reindex",
        "The knowledge index is available but has no current documents.",
    ),
    "knowledge_index_unavailable": (
        "error",
        "retry",
        "The knowledge index could not be inspected safely.",
    ),
    "reasoning_operational": ("ok", "none", "Codex App Server is operational."),
    "reasoning_not_configured": ("degraded", "setup_required", "Codex runtime is not configured."),
    "reasoning_runtime_missing": (
        "error",
        "setup_required",
        "The configured Codex runtime is unavailable to the Assistant process.",
    ),
    "reasoning_auth_unavailable": (
        "degraded",
        "authenticate_runtime",
        "Codex runtime authentication is unavailable.",
    ),
    "reasoning_protocol_incompatible": (
        "error",
        "setup_required",
        "The configured Codex runtime is incompatible with this Assistant version.",
    ),
    "reasoning_error": ("error", "retry", "The reasoning runtime could not be validated."),
    "assistant_runtime_unavailable": (
        "error",
        "setup_required",
        "Assistant runtime is blocked by storage, migrations, or configuration.",
    ),
    "status_unrecognized": (
        "unknown",
        "retry",
        "A backend status is not recognized by this addon version.",
    ),
}

_REMEDIATION_MESSAGES = {
    "none": "No action required.",
    "settings": "Review AI Assistant Settings.",
    "setup_required": "Review the controlled host setup; Odoo must not receive root privileges.",
    "retry": "Refresh diagnostics after correcting the related component.",
    "rescan": "Use the existing bounded source scan and refresh diagnostics.",
    "reindex": "Use the bounded knowledge maintenance operation when available.",
    "authenticate_runtime": "Authenticate Codex as the operating-system user running the Assistant Service.",
}


class AssistantDiagnostics(models.TransientModel):
    _name = "odoo.ai.assistant.diagnostics"
    _description = "Odoo AI Assistant Diagnostics"

    service_state = fields.Selection(
        [("ok", "Healthy"), ("error", "Error"), ("unknown", "Unknown")],
        readonly=True,
    )
    message = fields.Char(readonly=True)
    endpoint_state = fields.Char(readonly=True)
    readiness = fields.Char(readonly=True)
    diagnostics_checked_at = fields.Char(readonly=True)
    diagnostics_config_revision = fields.Integer(readonly=True)
    diagnostic_errors = fields.Text(readonly=True)
    diagnostic_warnings = fields.Text(readonly=True)
    diagnostic_ok = fields.Text(readonly=True)
    assistant_database_state = fields.Char(readonly=True)
    migrations_state = fields.Char(readonly=True)
    instance_id = fields.Char(readonly=True)
    instance_fingerprint = fields.Char(readonly=True)
    source_state = fields.Char(readonly=True)
    source_scan_status = fields.Char(readonly=True)
    source_scan_fingerprint = fields.Char(readonly=True)
    log_state = fields.Char(readonly=True)
    log_provider = fields.Char(readonly=True)
    reasoning_engine_state = fields.Char(readonly=True)
    reasoning_provider = fields.Char(readonly=True)
    reasoning_protocol = fields.Char(readonly=True)
    reasoning_runtime_version = fields.Char(readonly=True)
    reasoning_model = fields.Char(readonly=True)
    reasoning_setup_message = fields.Char(readonly=True)
    source_result = fields.Text(readonly=True)
    log_result = fields.Text(readonly=True)

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
        action = self.env["ir.actions.actions"]._for_xml_id("base.action_res_config_settings")
        action["context"] = {"module": "odoo_ai_assistant"}
        return action

    def action_rescan_source(self):
        self._require_admin()
        self.ensure_one()
        try:
            result = self._client().source_rescan()
        except AssistantServiceError as error:
            self.write({"source_result": self._error_message(error.code)})
            return {"type": "ir.actions.client", "tag": "reload"}
        self.write(
            {
                "source_state": str(result.get("state") or _("Unknown")),
                "source_scan_status": "succeeded" if result.get("scan_id") else "failed",
                "source_scan_fingerprint": str(result.get("fingerprint") or _("Unknown")),
                "source_result": _("Source scan completed: %(files)s files, %(stale)s stale.")
                % {
                    "files": (result.get("metrics") or {}).get("files_seen", 0),
                    "stale": (result.get("metrics") or {}).get("stale_files", 0),
                },
            }
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_test_source(self):
        self._require_admin()
        self.ensure_one()
        try:
            result = self._client().source_test()
        except AssistantServiceError as error:
            self.write({"source_result": self._error_message(error.code)})
            return {"type": "ir.actions.client", "tag": "reload"}
        candidate = result.get("candidate") or {}
        excerpt = result.get("excerpt") or {}
        lines = excerpt.get("lines") or []
        rendered = "\n".join(
            f"{line.get('number')}: {line.get('text')}"
            for line in lines
            if isinstance(line, dict)
        )
        self.write(
            {
                "source_result": _(
                    "Module: %(module)s\nFile: %(path)s\nLines: %(start)s-%(end)s\n"
                    "Fingerprint: %(fingerprint)s\n\n%(excerpt)s"
                )
                % {
                    "module": candidate.get("module") or _("Unknown"),
                    "path": candidate.get("logical_path") or _("Unknown"),
                    "start": candidate.get("start_line") or "?",
                    "end": candidate.get("end_line") or "?",
                    "fingerprint": candidate.get("fingerprint") or _("Unknown"),
                    "excerpt": rendered,
                }
            }
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_test_logs(self):
        self._require_admin()
        self.ensure_one()
        now = datetime.now(UTC)
        payload = {
            "from_ts": (now - timedelta(days=1)).isoformat(),
            "to_ts": now.isoformat(),
            "terms": ["Traceback"],
            "max_lines": 200,
            "max_bytes": 65_536,
        }
        try:
            result = self._client().logs_test(payload)
            rows = result.get("results") or []
            row = rows[0] if rows else None
            if not isinstance(row, dict):
                text = _("Log provider is operational; no traceback matched the test window.")
            else:
                fingerprint = row.get("traceback_fingerprint")
                if isinstance(fingerprint, str):
                    row = self._client().logs_traceback(fingerprint, max_bytes=16_384)
                text = _(
                    "Provider: %(provider)s\nFingerprint: %(fingerprint)s\n"
                    "Occurrences: %(count)s\n\n%(excerpt)s"
                ) % {
                    "provider": row.get("provider") or result.get("provider"),
                    "fingerprint": row.get("traceback_fingerprint") or _("None"),
                    "count": row.get("occurrence_count") or 1,
                    "excerpt": row.get("excerpt") or "",
                }
        except AssistantServiceError as error:
            self.write({"log_result": self._error_message(error.code)})
            return {"type": "ir.actions.client", "tag": "reload"}
        self.write(
            {
                "log_state": str(result.get("state") or _("Unknown")),
                "log_provider": str(result.get("provider") or _("Unknown")),
                "log_result": text,
            }
        )
        return {"type": "ir.actions.client", "tag": "reload"}

    def _require_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only system administrators can run diagnostics."))

    @api.model
    def _configured_value(self, parameter: str, environment_name: str) -> str | None:
        value = self.env["ir.config_parameter"].get_param(parameter)
        return value or os.environ.get(environment_name) or None

    @api.model
    def _client(self) -> AssistantServiceClient:
        service_url = self._configured_value(SERVICE_URL_PARAM, SERVICE_URL_ENV)
        if not service_url:
            raise AssistantServiceError("configuration_missing")
        secret_file = self._configured_value(SECRET_FILE_PARAM, SECRET_FILE_ENV)
        return AssistantServiceClient(base_url=service_url, shared_secret_file=secret_file)

    @api.model
    def _diagnostic_values(self):
        self._require_admin()
        unknown = _("Unknown")
        endpoint_state = (
            _("Configured")
            if self._configured_value(SERVICE_URL_PARAM, SERVICE_URL_ENV)
            else unknown
        )
        values = {
            "service_state": "unknown",
            "message": _("Assistant Service has not been checked."),
            "endpoint_state": endpoint_state,
            "readiness": unknown,
            "diagnostics_checked_at": unknown,
            "diagnostics_config_revision": 0,
            "diagnostic_errors": False,
            "diagnostic_warnings": False,
            "diagnostic_ok": False,
            "assistant_database_state": unknown,
            "migrations_state": unknown,
            "instance_id": unknown,
            "instance_fingerprint": unknown,
            "source_state": unknown,
            "source_scan_status": unknown,
            "source_scan_fingerprint": unknown,
            "log_state": unknown,
            "log_provider": unknown,
            "reasoning_engine_state": unknown,
            "reasoning_provider": unknown,
            "reasoning_protocol": unknown,
            "reasoning_runtime_version": unknown,
            "reasoning_model": unknown,
            "reasoning_setup_message": _(
                "Configure and test the Codex runtime from the Assistant setup boundary."
            ),
            "source_result": False,
            "log_result": False,
        }
        try:
            client = self._client()
            client.health()
            status = client.admin_status()
            matrix = client.diagnostics_matrix()
        except AssistantServiceError as error:
            message = self._error_message(error.code)
            values.update(service_state="error", message=message, diagnostic_errors=message)
            return values

        components = status.get("components") if isinstance(status.get("components"), dict) else {}
        database = components.get("assistant_database", {})
        migrations = components.get("migrations", {})
        instance = status.get("instance") if isinstance(status.get("instance"), dict) else {}
        source = components.get("source", {})
        logs = components.get("logs", {})
        reasoning = components.get("reasoning_engine", {})
        try:
            source_status = client.source_status()
        except AssistantServiceError:
            source_status = {}
        values.update(
            service_state="ok",
            message=_("Assistant Service responded successfully."),
            readiness=str(status.get("readiness") or unknown),
            assistant_database_state=str(database.get("state") or unknown),
            migrations_state=str(migrations.get("state") or unknown),
            instance_id=str(instance.get("instance_id") or unknown),
            instance_fingerprint=str(instance.get("fingerprint") or unknown),
            source_state=str(source.get("state") or unknown),
            source_scan_status=str(source_status.get("scan_status") or unknown),
            source_scan_fingerprint=str(source_status.get("fingerprint") or unknown),
            log_state=str(logs.get("state") or unknown),
            log_provider=str((instance.get("capabilities") or {}).get("log_provider") or unknown),
            reasoning_engine_state=str(reasoning.get("state") or unknown),
            reasoning_provider=str(reasoning.get("provider") or unknown),
            reasoning_protocol=str(reasoning.get("protocol") or unknown),
            reasoning_runtime_version=str(reasoning.get("runtime_version") or unknown),
            reasoning_model=str(reasoning.get("model") or unknown),
            reasoning_setup_message=self._reasoning_setup_message(reasoning.get("detail")),
        )
        values.update(self._matrix_values(matrix))
        return values

    @api.model
    def _matrix_values(self, payload):
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return self._invalid_matrix_values()
        readiness = payload.get("readiness")
        checked_at = payload.get("checked_at")
        revision = payload.get("config_revision")
        entries = payload.get("entries")
        if (
            readiness not in {"FULLY_READY", "DEGRADED", "ERROR"}
            or not isinstance(checked_at, str)
            or not checked_at
            or len(checked_at) > 64
            or type(revision) is not int
            or revision < 0
            or not isinstance(entries, list)
            or len(entries) > 32
        ):
            return self._invalid_matrix_values()

        grouped = {"error": [], "degraded": [], "ok": [], "unknown": []}
        rejected = False
        for item in entries:
            if not isinstance(item, dict):
                rejected = True
                continue
            key = item.get("key")
            reason = item.get("reason_code")
            state = item.get("state")
            remediation = item.get("remediation_kind")
            label = _DIAGNOSTIC_KEYS.get(key)
            presentation = _DIAGNOSTIC_REASON_PRESENTATION.get(reason)
            if label is None or presentation is None:
                rejected = True
                continue
            expected_state, expected_remediation, message = presentation
            if state != expected_state or remediation != expected_remediation:
                rejected = True
                continue
            remediation_message = _REMEDIATION_MESSAGES[expected_remediation]
            grouped[expected_state].append(
                _("%(label)s: %(message)s %(remediation)s")
                % {
                    "label": _(label),
                    "message": _(message),
                    "remediation": _(remediation_message),
                }
            )

        if rejected:
            grouped["unknown"].append(
                _("One or more diagnostic entries were omitted because their contract was not recognized.")
            )
        warnings = [*grouped["degraded"], *grouped["unknown"]]
        return {
            "readiness": readiness,
            "diagnostics_checked_at": checked_at,
            "diagnostics_config_revision": revision,
            "diagnostic_errors": "\n".join(grouped["error"]) or False,
            "diagnostic_warnings": "\n".join(warnings) or False,
            "diagnostic_ok": "\n".join(grouped["ok"]) or False,
        }

    @api.model
    def _invalid_matrix_values(self):
        return {
            "readiness": "ERROR",
            "diagnostic_errors": _(
                "Structured diagnostics response was invalid or incompatible with this addon version."
            ),
            "diagnostic_warnings": False,
            "diagnostic_ok": False,
        }

    @api.model
    def _reasoning_setup_message(self, detail):
        messages = {
            "operational": _("Codex App Server is operational."),
            "not_configured": _("Select the Codex runtime in the Assistant host setup, then test again."),
            "runtime_missing": _("The configured Codex runtime is unavailable to the Assistant Service."),
            "auth_unavailable": _(
                "Authenticate Codex as the operating-system user that runs the Assistant Service."
            ),
            "protocol_incompatible": _(
                "The configured Codex runtime is not compatible with this Assistant version."
            ),
            "error": _("Codex could not be tested. Review the sanitized Assistant Service diagnostics."),
        }
        return messages.get(
            detail,
            _("Configure and test the Codex runtime from the Assistant setup boundary."),
        )

    @api.model
    def _error_message(self, code: str) -> str:
        messages = {
            "configuration_missing": _("Assistant Service endpoint is not configured on the Odoo server."),
            "configuration_invalid": _("Assistant Service endpoint must be a valid loopback HTTP URL."),
            "authentication_unconfigured": _(
                "Assistant Service authentication is not configured on the Odoo server."
            ),
            "authentication_unavailable": _(
                "Assistant Service credentials are unavailable to the Odoo server."
            ),
            "authentication_rejected": _(
                "Assistant Service rejected the configured local credentials."
            ),
            "service_unavailable": _(
                "Assistant Service is unavailable at the configured local endpoint."
            ),
            "invalid_response": _("Assistant Service returned an invalid response."),
            "diagnostic_not_found": _("The requested diagnostic evidence was not found."),
            "diagnostic_unavailable": _("The requested diagnostic capability is unavailable."),
            "invalid_request": _("The diagnostic request was rejected."),
        }
        return messages.get(code, _("Assistant Service check failed."))
