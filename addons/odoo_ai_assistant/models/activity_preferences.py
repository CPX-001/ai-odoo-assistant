"""Per-user semantic activity presentation preferences.

These settings affect only rendering/presentation. They never alter capability discovery,
policy, approval, ACLs, execution authority or audit persistence.
"""

from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

DETAIL_LEVELS = frozenset({"compact", "normal", "detailed", "diagnostic"})
REASONING_SUMMARY_LEVELS = frozenset({"off", "concise", "detailed"})
DEFAULT_DETAIL_LEVEL = "normal"
DEFAULT_TRANSIENT_THRESHOLD_MS = 1200
DEFAULT_BATCH_PAGE_SIZE = 5
DEFAULT_REASONING_SUMMARY = "concise"
MIN_TRANSIENT_THRESHOLD_MS = 0
MAX_TRANSIENT_THRESHOLD_MS = 5000
MIN_BATCH_PAGE_SIZE = 1
MAX_BATCH_PAGE_SIZE = 20
MAX_RENDERED_ACTIVITY_ITEMS = 100
MAX_RENDERED_BATCH_ROWS = 100
MAX_REASONING_SUMMARY_CHARS = 2000


class AssistantUserPreference(models.Model):
    _inherit = "odoo.ai.user.preference"

    activity_detail_level = fields.Selection(
        selection=[
            ("compact", "Compact"),
            ("normal", "Normal"),
            ("detailed", "Detailed"),
            ("diagnostic", "Diagnostic"),
        ],
        string="Assistant activity detail",
        default=DEFAULT_DETAIL_LEVEL,
    )
    activity_transient_threshold_ms = fields.Integer(
        string="Assistant transient activity threshold (ms)",
        default=DEFAULT_TRANSIENT_THRESHOLD_MS,
    )
    activity_batch_page_size = fields.Integer(
        string="Assistant activity batch page size",
        default=DEFAULT_BATCH_PAGE_SIZE,
    )
    activity_show_technical_names = fields.Boolean(
        string="Show Assistant technical names",
        default=False,
    )
    activity_show_step_durations = fields.Boolean(
        string="Show Assistant step durations",
        default=False,
    )
    activity_reasoning_summary = fields.Selection(
        selection=[
            ("off", "Off"),
            ("concise", "Concise"),
            ("detailed", "Detailed"),
        ],
        string="Assistant reasoning summary",
        default=DEFAULT_REASONING_SUMMARY,
    )

    @api.constrains("activity_transient_threshold_ms", "activity_batch_page_size")
    def _check_activity_presentation_bounds(self):
        for record in self:
            threshold = record.activity_transient_threshold_ms
            page_size = record.activity_batch_page_size
            if not MIN_TRANSIENT_THRESHOLD_MS <= threshold <= MAX_TRANSIENT_THRESHOLD_MS:
                raise ValidationError("Invalid Assistant activity transient threshold.")
            if not MIN_BATCH_PAGE_SIZE <= page_size <= MAX_BATCH_PAGE_SIZE:
                raise ValidationError("Invalid Assistant activity batch page size.")

    @api.model
    def activity_presentation_preferences(self):
        if not self.env.user._is_internal():
            return _error("access_denied")
        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        return {
            "ok": True,
            "detail_level": _detail_level(preference),
            "transient_threshold_ms": _threshold(preference),
            "batch_page_size": _page_size(preference),
            "show_technical_names": bool(preference.activity_show_technical_names) if preference else False,
            "show_step_durations": bool(preference.activity_show_step_durations) if preference else False,
            "reasoning_summary": _reasoning_summary(preference),
            "limits": {
                "max_rendered_activity_items": MAX_RENDERED_ACTIVITY_ITEMS,
                "max_rendered_batch_rows": MAX_RENDERED_BATCH_ROWS,
                "max_reasoning_summary_chars": MAX_REASONING_SUMMARY_CHARS,
            },
        }

    @api.model
    def set_activity_presentation_preferences(self, values):
        if not self.env.user._is_internal() or not isinstance(values, dict):
            return _error("invalid_context")
        allowed = {
            "detail_level",
            "transient_threshold_ms",
            "batch_page_size",
            "show_technical_names",
            "show_step_durations",
            "reasoning_summary",
        }
        if set(values) - allowed:
            return _error("invalid_context")
        normalized = {}
        if "detail_level" in values:
            if values["detail_level"] not in DETAIL_LEVELS:
                return _error("invalid_context")
            normalized["activity_detail_level"] = values["detail_level"]
        if "transient_threshold_ms" in values:
            value = values["transient_threshold_ms"]
            if type(value) is not int or not MIN_TRANSIENT_THRESHOLD_MS <= value <= MAX_TRANSIENT_THRESHOLD_MS:
                return _error("invalid_context")
            normalized["activity_transient_threshold_ms"] = value
        if "batch_page_size" in values:
            value = values["batch_page_size"]
            if type(value) is not int or not MIN_BATCH_PAGE_SIZE <= value <= MAX_BATCH_PAGE_SIZE:
                return _error("invalid_context")
            normalized["activity_batch_page_size"] = value
        for request_key, field_name in (
            ("show_technical_names", "activity_show_technical_names"),
            ("show_step_durations", "activity_show_step_durations"),
        ):
            if request_key in values:
                if type(values[request_key]) is not bool:
                    return _error("invalid_context")
                normalized[field_name] = values[request_key]
        if "reasoning_summary" in values:
            if values["reasoning_summary"] not in REASONING_SUMMARY_LEVELS:
                return _error("invalid_context")
            normalized["activity_reasoning_summary"] = values["reasoning_summary"]

        preference = self.search([("user_id", "=", self.env.uid)], limit=1)
        try:
            if preference:
                preference.write(normalized)
            else:
                preference = self.create({"user_id": self.env.uid, **normalized})
        except ValidationError:
            return _error("invalid_context")
        return self.activity_presentation_preferences()


def _detail_level(preference):
    value = preference.activity_detail_level if preference else None
    return value if value in DETAIL_LEVELS else DEFAULT_DETAIL_LEVEL


def _threshold(preference):
    value = preference.activity_transient_threshold_ms if preference else None
    if type(value) is int and MIN_TRANSIENT_THRESHOLD_MS <= value <= MAX_TRANSIENT_THRESHOLD_MS:
        return value
    return DEFAULT_TRANSIENT_THRESHOLD_MS


def _page_size(preference):
    value = preference.activity_batch_page_size if preference else None
    if type(value) is int and MIN_BATCH_PAGE_SIZE <= value <= MAX_BATCH_PAGE_SIZE:
        return value
    return DEFAULT_BATCH_PAGE_SIZE


def _reasoning_summary(preference):
    value = preference.activity_reasoning_summary if preference else None
    return value if value in REASONING_SUMMARY_LEVELS else DEFAULT_REASONING_SUMMARY


def _error(code):
    return {"error": {"code": code}, "ok": False}
