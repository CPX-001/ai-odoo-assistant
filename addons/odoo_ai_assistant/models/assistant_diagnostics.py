"""Administrator-only Odoo view of Assistant Service health."""

import os

from odoo import _, api, fields, models

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

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        values.update(self._diagnostic_values())
        return values

    def action_refresh(self):
        self.ensure_one()
        self.write(self._diagnostic_values())
        return {"type": "ir.actions.client", "tag": "reload"}

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
        values.update(
            service_state="ok",
            message=_("Assistant Service responded successfully."),
            readiness=str(status.get("readiness") or unknown),
            assistant_database_state=str(database.get("state") or unknown),
            migrations_state=str(migrations.get("state") or unknown),
            instance_id=str(instance.get("instance_id") or unknown),
            instance_fingerprint=str(instance.get("fingerprint") or unknown),
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
        }
        return messages.get(code, _("Assistant Service check failed."))
