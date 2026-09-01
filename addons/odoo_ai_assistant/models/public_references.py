"""Resolve typed Assistant references under the effective Odoo user.

The browser receives no arbitrary URL or route from the model. It submits only one of the closed
reference descriptors below and the host revalidates current user access, group/menu visibility,
record existence and installed schema before returning a second closed navigation descriptor.
"""

from __future__ import annotations

import re

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError, MissingError

from ..services.turn_context import agent_model_is_eligible, visible_query_fields

_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_REFERENCES = 50
_MAX_PRESENTATION_FIELDS = 3
_MAX_LABEL = 160
_MAX_DESCRIPTION = 240
_VIEW_TYPES = frozenset({"list", "form", "kanban", "calendar", "graph", "pivot", "activity"})
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
        return _model_reference(env, model) if model else None
    if kind == "odoo_action":
        if set(raw) != {"kind", "action_id"}:
            return None
        return _action_reference(env, raw.get("action_id"), kind="odoo_action")
    if kind == "odoo_view":
        if set(raw) != {"kind", "view_id"}:
            return None
        return _view_reference(env, raw.get("view_id"))
    if kind == "odoo_menu":
        if set(raw) != {"kind", "menu_id"}:
            return None
        return _menu_reference(env, raw.get("menu_id"))
    if kind == "odoo_setting":
        if set(raw) != {"kind", "action_id", "setting_field"}:
            return None
        return _setting_reference(env, raw.get("action_id"), raw.get("setting_field"))
    return None


def _model(value):
    return value if isinstance(value, str) and _MODEL.fullmatch(value) else None


def _field(value):
    return value if isinstance(value, str) and _FIELD.fullmatch(value) else None


def _model_set(env, model, *, allow_transient=False):
    if not isinstance(model, str) or model not in env:
        return None
    if not allow_transient and not agent_model_is_eligible(env, model):
        return None
    try:
        model_set = env[model]
        if getattr(model_set, "_abstract", False):
            return None
        if getattr(model_set, "_transient", False) and not allow_transient:
            return None
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
        "description": _description(f"Abrir registros de {_model_label(env, model, model_set)}"),
        "navigation": {"mode": "model", "model": model},
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
        "description": _description(f"Abrir {display_name}"),
        "navigation": {"mode": "record", "model": model, "record_id": record_id},
    }


def _group_allowed(env, record):
    if "groups_id" not in record._fields:
        return True
    try:
        groups = record.groups_id
        return not groups or bool(groups & env.user.groups_id)
    except Exception:  # noqa: BLE001 - group metadata failure is fail closed
        return False


def _action_record(env, action_id):
    if type(action_id) is not int or action_id <= 0:
        return None
    try:
        action = (
            env["ir.actions.act_window"]
            .with_user(SUPERUSER_ID)
            .browse(action_id)
            .exists()
        )
        if (
            not action
            or action.id != action_id
            or action.type != "ir.actions.act_window"
            or not _action_metadata_allowed(env, action_id)
            or not _group_allowed(env, action)
        ):
            return None
        if _model_set(
            env,
            action.res_model,
            allow_transient=action.res_model == "res.config.settings",
        ) is None:
            return None
        return action
    except (AccessError, MissingError, KeyError):
        return None


def _visible_action_ids(env):
    menu_ids = _visible_menu_ids(env)
    if not menu_ids:
        return set()
    try:
        menus = env["ir.ui.menu"].browse(list(menu_ids)).exists()
        return {
            menu.action.id
            for menu in menus
            if menu.action and menu.action._name == "ir.actions.act_window"
        }
    except (AccessError, MissingError, KeyError):
        return set()


def _action_metadata_allowed(env, action_id):
    if action_id in _visible_action_ids(env):
        return True
    try:
        env["ir.actions.act_window"].browse(action_id).check_access("read")
    except (AccessError, MissingError, KeyError):
        return False
    return True


def _action_reference(env, action_id, *, kind, menu_id=None):
    action = _action_record(env, action_id)
    if action is None:
        return None
    label = _label(action.name, action.res_model)
    result = {
        "kind": kind,
        "action_id": action.id,
        "model": action.res_model,
        "label": label,
        "description": _description(f"Abrir {label} en Odoo"),
        "navigation": {"mode": "action", "action_id": action.id},
    }
    if type(menu_id) is int and menu_id > 0:
        result["menu_id"] = menu_id
    return result


def _view_reference(env, view_id):
    if type(view_id) is not int or view_id <= 0:
        return None
    try:
        view = env["ir.ui.view"].browse(view_id).exists()
        if not view or view.id != view_id or not _group_allowed(env, view):
            return None
        view.check_access("read")
        view_type = "list" if view.type == "tree" else view.type
        if view_type not in _VIEW_TYPES or _model_set(env, view.model) is None:
            return None
    except (AccessError, MissingError, KeyError):
        return None
    label = _label(view.name, view.model)
    return {
        "kind": "odoo_view",
        "view_id": view.id,
        "model": view.model,
        "label": label,
        "description": _description(f"Abrir la vista {view_type} de {view.model}"),
        "navigation": {
            "mode": "view",
            "model": view.model,
            "view_id": view.id,
            "view_type": view_type,
        },
    }


def _visible_menu_ids(env):
    try:
        values = env["ir.ui.menu"]._visible_menu_ids()
    except Exception:  # noqa: BLE001 - menu visibility is a hard host boundary
        return set()
    return {value for value in values if type(value) is int and value > 0}


def _menu_reference(env, menu_id):
    if type(menu_id) is not int or menu_id <= 0 or menu_id not in _visible_menu_ids(env):
        return None
    try:
        menu = env["ir.ui.menu"].browse(menu_id).exists()
        if not menu or menu.id != menu_id:
            return None
        menu.check_access("read")
        action = menu.action
        if not action or action._name != "ir.actions.act_window":
            return None
    except (AccessError, MissingError, KeyError):
        return None
    resolved = _action_reference(env, action.id, kind="odoo_menu", menu_id=menu.id)
    if resolved is None:
        return None
    resolved["label"] = _label(menu.name, resolved["label"])
    parent = _label(menu.parent_id.name, "") if menu.parent_id else ""
    resolved["description"] = _description(
        f"Menú visible en {parent}" if parent else "Menú visible de Odoo"
    )
    return resolved


def _setting_reference(env, action_id, setting_field):
    field = _field(setting_field)
    action = _action_record(env, action_id)
    if field is None or action is None or action.res_model != "res.config.settings":
        return None
    try:
        metadata = env["res.config.settings"].fields_get(
            allfields=[field], attributes=["string", "help", "type"]
        )
        definition = metadata.get(field)
        if not isinstance(definition, dict):
            return None
    except (AccessError, MissingError, KeyError):
        return None
    label = _label(definition.get("string"), field)
    return {
        "kind": "odoo_setting",
        "action_id": action.id,
        "setting_field": field,
        "model": "res.config.settings",
        "label": label,
        "description": _description(
            definition.get("help"), f"Opción instalada de Configuración: {label}"
        ),
        "navigation": {"mode": "action", "action_id": action.id},
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
    return isinstance(description, dict) and description.get("type") in _SAFE_FIELD_TYPES


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


def _description(value, fallback=""):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = " ".join(text.split())
    if not text:
        text = fallback
    return text[:_MAX_DESCRIPTION]


def _error(code):
    return {"error": {"code": code}, "ok": False}
