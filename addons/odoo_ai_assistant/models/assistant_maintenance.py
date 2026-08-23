"""Odoo-native M7 maintenance actions with locally trusted rendering."""

from __future__ import annotations

from odoo import _, api, fields, models

from ..services import AssistantServiceError

_OPERATION_LABELS = {
    "readiness_test": "Readiness test",
    "source_rescan": "Source rescan",
    "source_test": "Source test",
    "logs_test": "Logs test",
    "knowledge_reindex": "Knowledge reindex",
    "reasoning_test": "Codex test",
    "action_self_test": "ACTION self-test",
    "configuration_revalidate": "Configuration revalidation",
}

_RESULT_MESSAGES = {
    "readiness_test": {
        "readiness_ok": "All required readiness checks are healthy.",
        "readiness_degraded": "Readiness is degraded; review Diagnostics warnings.",
        "readiness_error": "Readiness has a blocking error; review Diagnostics errors.",
        "readiness_test_failed": "Readiness could not be tested safely.",
    },
    "source_rescan": {
        "source_rescan_succeeded": "The bounded source rescan completed.",
        "source_rescan_failed": "The bounded source rescan failed.",
        "maintenance_job_abandoned": (
            "The previous source rescan did not complete and can be retried."
        ),
    },
    "source_test": {
        "source_test_succeeded": "The bounded source evidence test succeeded.",
        "source_test_failed": "The bounded source evidence test failed.",
    },
    "logs_test": {
        "logs_test_succeeded": "The configured bounded log provider test succeeded.",
        "logs_test_failed": "The configured bounded log provider test failed.",
    },
    "knowledge_reindex": {
        "knowledge_reindex_succeeded": "Knowledge was rebuilt from the configured sources.",
        "knowledge_reindex_incomplete": (
            "Knowledge rebuild was incomplete and was not committed."
        ),
        "knowledge_sources_unconfigured": (
            "No knowledge sources are configured for maintenance."
        ),
        "knowledge_source_limit": (
            "The configured knowledge source count exceeds the maintenance bound."
        ),
        "knowledge_instance_unavailable": (
            "No current Odoo instance profile is available for knowledge."
        ),
        "knowledge_reindex_failed": "Knowledge could not be rebuilt safely.",
        "maintenance_job_abandoned": (
            "The previous knowledge rebuild did not complete and can be retried."
        ),
    },
    "reasoning_test": {
        "reasoning_operational": "Codex App Server is operational.",
        "reasoning_not_configured": "Codex runtime is not configured.",
        "reasoning_runtime_missing": "The configured Codex runtime is unavailable.",
        "reasoning_auth_unavailable": (
            "Codex authentication is unavailable for the service user."
        ),
        "reasoning_protocol_incompatible": (
            "The Codex protocol is incompatible with this Assistant version."
        ),
        "reasoning_error": "Codex could not be validated safely.",
    },
    "action_self_test": {
        "action_self_test_succeeded": (
            "ACTION authority and Assistant-side storage are ready."
        ),
        "action_authority_unavailable": (
            "ACTION authority is not provisioned for the service."
        ),
        "action_store_unavailable": "ACTION Assistant-side storage is unavailable.",
    },
    "configuration_revalidate": {
        "configuration_valid": "The current effective configuration remains valid.",
        "configuration_invalid": (
            "The current configuration no longer satisfies host boundaries."
        ),
        "configuration_unavailable": "Configuration could not be revalidated safely.",
    },
}

_MAINTENANCE_ERROR_MESSAGES = {
    "maintenance_job_active": "A job for this maintenance operation is already active.",
    "maintenance_job_not_found": "The requested maintenance job no longer exists.",
    "maintenance_unavailable": "Maintenance state is currently unavailable.",
    "maintenance_invalid": "The maintenance request was rejected.",
}

_JOB_STATES = {"queued", "running", "succeeded", "failed"}


class AssistantMaintenance(models.TransientModel):
    _inherit = "odoo.ai.assistant.diagnostics"

    maintenance_last_result = fields.Text(readonly=True)
    maintenance_latest = fields.Text(readonly=True)
    maintenance_active_jobs = fields.Text(readonly=True)

    @api.model
    def _diagnostic_values(self):
        values = super()._diagnostic_values()
        try:
            status = self._client().maintenance_status()
        except (AssistantServiceError, AttributeError):
            return values
        values.update(self._maintenance_status_values(status))
        return values

    def action_maintenance_readiness_test(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_readiness_test(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_source_rescan(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_source_rescan(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_source_test(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_source_test(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_logs_test(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_logs_test(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_knowledge_reindex(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_knowledge_reindex(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_reasoning_test(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_reasoning_test(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_action_self_test(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_action_self_test(
                self._maintenance_actor_payload()
            )
        )

    def action_maintenance_configuration_revalidate(self):
        self._require_admin()
        self.ensure_one()
        return self._execute_maintenance(
            lambda: self._client().maintenance_configuration_revalidate(
                self._maintenance_actor_payload()
            )
        )

    def _execute_maintenance(self, callback):
        """Execute one fixed Python callback; no operation name comes from the browser."""

        self._require_admin()
        self.ensure_one()
        try:
            payload = callback()
        except AssistantServiceError as error:
            self.write({"maintenance_last_result": self._maintenance_error_message(error)})
            return {"type": "ir.actions.client", "tag": "reload"}
        return self._apply_maintenance_result(payload)

    def _apply_maintenance_result(self, payload):
        self._require_admin()
        self.ensure_one()
        rendered = self._render_maintenance_item(payload)
        if rendered is None:
            rendered = _("Maintenance returned an unrecognized bounded result.")
        values = {"maintenance_last_result": rendered}
        try:
            values.update(self._maintenance_status_values(self._client().maintenance_status()))
        except AssistantServiceError:
            pass
        self.write(values)
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _maintenance_actor_payload(self):
        self._require_admin()
        return {
            "actor": {
                "odoo_uid": self.env.uid,
                "odoo_database": self.env.cr.dbname,
            }
        }

    @api.model
    def _maintenance_status_values(self, payload):
        if not isinstance(payload, dict):
            return {}
        latest = payload.get("latest")
        active = payload.get("active_jobs")
        if (
            not isinstance(latest, list)
            or len(latest) > 8
            or not isinstance(active, list)
            or len(active) > 2
        ):
            return {
                "maintenance_latest": _("Maintenance status contract was not recognized."),
                "maintenance_active_jobs": False,
            }

        latest_lines = []
        active_lines = []
        rejected = False
        for item in latest:
            rendered = self._render_maintenance_item(item)
            if rendered is None:
                rejected = True
            else:
                latest_lines.append(rendered)
        for item in active:
            rendered = self._render_maintenance_item(item)
            if rendered is None:
                rejected = True
            else:
                active_lines.append(rendered)
        if rejected:
            latest_lines.append(
                _(
                    "One or more maintenance results were omitted because their "
                    "contract was unknown."
                )
            )
        return {
            "maintenance_latest": "\n".join(latest_lines) or False,
            "maintenance_active_jobs": "\n".join(active_lines) or False,
        }

    @api.model
    def _render_maintenance_item(self, payload):
        if not isinstance(payload, dict):
            return None
        operation = payload.get("operation")
        state = payload.get("state")
        result_code = payload.get("result_code")
        if (
            not isinstance(operation, str)
            or operation not in _OPERATION_LABELS
            or not isinstance(state, str)
            or state not in _JOB_STATES
        ):
            return None
        if state in {"queued", "running"}:
            if result_code is not None:
                return None
            state_message = _("queued") if state == "queued" else _("running")
            return _("%(operation)s: %(state)s.") % {
                "operation": _(_OPERATION_LABELS[operation]),
                "state": state_message,
            }
        messages = _RESULT_MESSAGES[operation]
        if not isinstance(result_code, str) or result_code not in messages:
            return None
        return _("%(operation)s: %(message)s") % {
            "operation": _(_OPERATION_LABELS[operation]),
            "message": _(messages[result_code]),
        }

    @api.model
    def _maintenance_error_message(self, error):
        if not isinstance(error, AssistantServiceError):
            return _("Maintenance failed.")
        if error.code in _MAINTENANCE_ERROR_MESSAGES:
            return _(_MAINTENANCE_ERROR_MESSAGES[error.code])
        return self._error_message(error.code)
