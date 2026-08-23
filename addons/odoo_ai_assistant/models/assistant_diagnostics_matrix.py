"""M7 hardened rendering for the structured diagnostics matrix."""

from odoo import _, api, models

from .assistant_diagnostics import (
    _DIAGNOSTIC_KEYS,
    _DIAGNOSTIC_REASON_PRESENTATION,
    _REMEDIATION_MESSAGES,
)

_PROVENANCE_LABELS = {
    "explicit_override": "admin override",
    "runtime": "runtime",
    "supervisor": "host setup",
    "config": "configuration",
    "hint": "hint",
    "unknown": "unknown",
}


class AssistantDiagnosticsMatrixRenderer(models.TransientModel):
    _inherit = "odoo.ai.assistant.diagnostics"

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
            provenance = item.get("provenance")
            if not all(isinstance(value, str) for value in (key, reason, state, remediation)):
                rejected = True
                continue
            if provenance is not None and not isinstance(provenance, str):
                rejected = True
                continue
            label = _DIAGNOSTIC_KEYS.get(key)
            presentation = _DIAGNOSTIC_REASON_PRESENTATION.get(reason)
            if label is None or presentation is None:
                rejected = True
                continue
            expected_state, expected_remediation, message = presentation
            if state != expected_state or remediation != expected_remediation:
                rejected = True
                continue
            if provenance is not None and provenance not in _PROVENANCE_LABELS:
                rejected = True
                continue

            remediation_message = _REMEDIATION_MESSAGES[expected_remediation]
            provenance_suffix = ""
            if provenance is not None:
                provenance_suffix = _(" Provenance: %(provenance)s.") % {
                    "provenance": _(_PROVENANCE_LABELS[provenance])
                }
            grouped[expected_state].append(
                _("%(label)s: %(message)s %(remediation)s%(provenance)s")
                % {
                    "label": _(label),
                    "message": _(message),
                    "remediation": _(remediation_message),
                    "provenance": provenance_suffix,
                }
            )

        if rejected:
            grouped["unknown"].append(
                _(
                    "One or more diagnostic entries were omitted because their contract "
                    "was not recognized."
                )
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
