"""Resolve typed Assistant references under the effective Odoo user.

The browser receives no arbitrary route/action payload from the model. It submits only a closed
reference descriptor and the host revalidates model eligibility, record existence and current read
access before returning a presentation/navigation descriptor.
"""

from __future__ import annotations

import re

from odoo import api, models
from odoo.exceptions import AccessError, MissingError

from ..services.turn_context import agent_model_is_eligible, visible_query_fields

_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_MAX_REFERENCES = 50
_MAX_PRESENTATION_FIELDS = 3
_MAX_LABEL = 160
_SAFE_FIELD_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "integer",
        "many2one",
        "monetary",
        "selection",
    }
)
_FIELD_PRIORITY = (
    "name",
    "code",
    "ref",
    "reference",
    "state",
    "date",
    "date_order",
    "invoice_date",
    "create_date",
)


class AssistantUserPreference(models.Model):
    _inherit = "odoo.ai.user.preference"

    @api.model
    def resolve_public_references(self, references):
        if not self.env.user._is_internal() or not isinstance(references, list):
            return _error("invalid_context")
        if not 1 <= len(references) <= _MAX_REFERENCES:
            return _error("invalid_context")
        resolved = []
        for raw in references:
            item = _resolve_reference(self.env, raw)
            if item is None:
                resolved.append({"ok": False, "error": {"code": "reference_unavailable"}})
            else:
                resolved.append({"ok": True, "reference": item})
        return {"ok": True, "references": resolved}


def _resolve_reference(env, raw):
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if kind == "odoo_record":
        if set(raw) != {"kind", "model", "record_id"}:
            return None
        model = _model(raw.get("model"))
        record_id = raw.get("record_id")
        if model is None or type(record_id) is not int or record_id <= 0:
            return None
        return _record_reference(env, model, record_id)
    if kind == "odoo_model":
        if set(raw) != {"kind", "model"}:
            return None
        model = _model(raw.get("model"))
        if model is None:
            return None
        return _model_reference(env, model)
    return None


def _model(value):
    return value if isinstance(value, str) and _MODEL.fullmatch(value) else None


def _model_set(env, model):
    if not agent_model_is_eligible(env, model):
        return None
    try:
        model_set = env[model]
        model_set.browse().check_access("read")
    except (AccessError, MissingError, KeyError):
        return None
    return model_set


def _model_label(env, model, model_set):
    try:
        record = env["ir.model"]._get(model)
        value = record.name if record else None
    except Exception:  # noqa: BLE001 - presentation fallback only
        value = None
    text = value or getattr(model_set, "_description", None) or model
    return _label(text, model)


def _model_reference(env, model):
    model_set = _model_set(env, model)
    if model_set is None:
        return None
    return {
        "kind": "odoo_model",
        "model": model,
        "label": _model_label(env, model, model_set),
        "navigation": {"view_type": "list"},
    }


def _record_reference(env, model, record_id):
    model_set = _model_set(env, model)
    if model_set is None:
        return None
    try:
        record = model_set.browse(record_id).exists()
        if not record or record.id != record_id:
            return None
        record.check_access("read")
        display_name = _label(record.display_name, f"#{record_id}")
        fields = _presentation_fields(env, model, record)
    except (AccessError, MissingError, KeyError):
        return None
    return {
        "kind": "odoo_record",
        "model": model,
        "record_id": record_id,
        "label": display_name,
        "model_label": _model_label(env, model, model_set),
        "fields": fields,
        "navigation": {"view_type": "form"},
    }


def _presentation_fields(env, model, record):
    try:
        visible = set(visible_query_fields(env, model))
        metadata = record.fields_get(
            allfields=list(visible),
            attributes=["string", "type"],
        )
    except Exception:  # noqa: BLE001 - generic presentation is optional
        return []
    candidates = []
    seen = set()
    for name in _FIELD_PRIORITY:
        description = metadata.get(name)
        if name in visible and _candidate(description) and name not in seen:
            candidates.append(name)
            seen.add(name)
    for name, description in metadata.items():
        if len(candidates) >= _MAX_PRESENTATION_FIELDS:
            break
        if name not in seen and _candidate(description):
            candidates.append(name)
            seen.add(name)
    candidates = candidates[:_MAX_PRESENTATION_FIELDS]
    if not candidates:
        return []
    try:
        values = record.read(candidates, load=None)[0]
    except Exception:  # noqa: BLE001 - row detail is optional
        return []
    result = []
    for name in candidates:
        value = _display_value(values.get(name))
        if value in (None, ""):
            continue
        result.append(
            {
                "name": name,
                "label": _label(metadata[name].get("string"), name),
                "value": value,
            }
        )
    return result[:_MAX_PRESENTATION_FIELDS]


def _candidate(description):
    return (
        isinstance(description, dict)
        and description.get("type") in _SAFE_FIELD_TYPES
    )


def _display_value(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and type(value[0]) is int:
            return _label(value[1], str(value[0]))
        return None
    if isinstance(value, str):
        return _label(value, "")
    return _label(str(value), "")


def _label(value, fallback):
    text = " ".join(str(value or "").split())
    if not text:
        text = str(fallback)
    return text[:_MAX_LABEL]


def _error(code):
    return {"error": {"code": code}, "ok": False}
