"""Administrator-only Odoo view of Assistant Service health."""

import os
from datetime import UTC, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..services import AssistantServiceClient, AssistantServiceError

SERVICE_URL_PARAM = "odoo_ai_assistant.service_url"
SECRET_FILE_PARAM = "odoo_ai_assistant.shared_secret_file"
SERVICE_URL_ENV = "ODOO_AI_SERVICE_URL"
SECRET_FILE_ENV = "ODOO_AI_SHARED_SECRET_FILE"


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
    assistant_database_state = fields.Char(readonly=True)
    migrations_state = fields.Char(readonly=True)
    instance_id = fields.Char(readonly=True)
    instance_fingerprint = fields.Char(readonly=True)
    source_state = fields.Char(readonly=True)
    source_scan_status = fields.Char(readonly=True)
    source_scan_fingerprint = fields.Char(readonly=True)
    log_state = fields.Char(readonly=True)
    log_provider = fields.Char(readonly=True)
    source_result = fields.Text(readonly=True)
    log_result = fields.Text(readonly=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        values.update(self._diagnostic_values())
        return values

    def action_refresh(self):
        self._require_admin()
        self.ensure_one()
        self.write(self._diagnostic_values())
        return {"type": "ir.actions.client", "tag": "reload"}

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
                "source_scan_fingerprint": str(
                    result.get("fingerprint") or _("Unknown")
                ),
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
                    row = self._client().logs_traceback(
                        fingerprint, max_bytes=16_384
                    )
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
        return AssistantServiceClient(
            base_url=service_url,
            shared_secret_file=secret_file,
        )

    @api.model
    def _diagnostic_values(self):
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
            "assistant_database_state": unknown,
            "migrations_state": unknown,
            "instance_id": unknown,
            "instance_fingerprint": unknown,
            "source_state": unknown,
            "source_scan_status": unknown,
            "source_scan_fingerprint": unknown,
            "log_state": unknown,
            "log_provider": unknown,
            "source_result": False,
            "log_result": False,
        }
        try:
            client = self._client()
            client.health()
            status = client.admin_status()
        except AssistantServiceError as error:
            values.update(service_state="error", message=self._error_message(error.code))
            return values

        components = status.get("components") if isinstance(status.get("components"), dict) else {}
        database = components.get("assistant_database", {})
        migrations = components.get("migrations", {})
        instance = status.get("instance") if isinstance(status.get("instance"), dict) else {}
        source = components.get("source", {})
        logs = components.get("logs", {})
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
            log_provider=str(
                (instance.get("capabilities") or {}).get("log_provider") or unknown
            ),
        )
        return values

    @api.model
    def _error_message(self, code: str) -> str:
        messages = {
            "configuration_missing": _(
                "Assistant Service endpoint is not configured on the Odoo server."
            ),
            "configuration_invalid": _(
                "Assistant Service endpoint must be a valid loopback HTTP URL."
            ),
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
