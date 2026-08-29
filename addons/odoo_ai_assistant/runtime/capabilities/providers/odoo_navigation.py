"""Bounded host-resolved contextual navigation for the embedded Assistant.

The model supplies only a semantic query and optional reference kinds.  Odoo discovers concrete
models/actions/views/menus/settings under the effective non-sudo Environment and returns bounded
presentation references.  The concrete identifiers are results, never capability arguments; the
browser must send a selected reference back to Odoo for fresh validation before navigation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ....services.turn_context import agent_model_is_eligible, search_agent_models
from ..contracts import CapabilityContext, CapabilityEffect, CapabilityRisk
from ..decorators import tool

_KINDS = ("odoo_model", "odoo_action", "odoo_view", "odoo_menu", "odoo_setting")
_VIEW_TYPES = frozenset({"list", "form", "kanban", "calendar", "graph", "pivot", "activity"})
_MAX_RESULTS = 12
_MAX_QUERY = 160
_MAX_DESCRIPTION = 240
_MAX_CANDIDATES_PER_TOKEN = 48
_MAX_TOKENS = 6

_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(_KINDS)},
        "label": {"type": "string", "minLength": 1, "maxLength": 160},
        "description": {"type": "string", "maxLength": _MAX_DESCRIPTION},
        "model": {"type": ["string", "null"]},
        "action_id": {"type": ["integer", "null"]},
        "view_id": {"type": ["integer", "null"]},
        "menu_id": {"type": ["integer", "null"]},
        "setting_field": {"type": ["string", "null"]},
    },
    "required": [
        "kind",
        "label",
        "description",
        "model",
        "action_id",
        "view_id",
        "menu_id",
        "setting_field",
    ],
    "additionalProperties": False,
}


@tool(
    name="odoo.resolve_navigation",
    title="Buscar dónde abrirlo en Odoo",
    description=(
        "Resolve a semantic request such as 'contacts', 'customer invoices' or 'settings for taxes' "
        "to a bounded list of Odoo models, window actions, views, visible menus and installed "
        "configuration options. Supply only the semantic query; concrete Odoo ids are resolved by "
        "the host and are never accepted as authority from the model."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY},
            "kinds": {
                "type": "array",
                "items": {"type": "string", "enum": list(_KINDS)},
                "maxItems": len(_KINDS),
                "uniqueItems": True,
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY},
            "references": {
                "type": "array",
                "items": _REFERENCE_SCHEMA,
                "maxItems": _MAX_RESULTS,
            },
        },
        "required": ["query", "references"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("odoo", "navigation", "ui", "settings"),
    max_calls=4,
    max_input_bytes=4 * 1024,
    max_output_bytes=24 * 1024,
)
def resolve_navigation(context: CapabilityContext, arguments):
    env = context.env
    if getattr(env, "su", True):
        raise RuntimeError("superuser_context_forbidden")
    query = _query(arguments.get("query"))
    requested = arguments.get("kinds")
    kinds = tuple(requested) if isinstance(requested, list) and requested else _KINDS
    limit = arguments.get("limit", 8)
    if type(limit) is not int or not 1 <= limit <= _MAX_RESULTS:
        raise RuntimeError("navigation_request_invalid")

    candidates = []
    if "odoo_model" in kinds:
        candidates.extend(_models(env, query, limit))
    if "odoo_action" in kinds:
        candidates.extend(_actions(env, query))
    if "odoo_view" in kinds:
        candidates.extend(_views(env, query))
    if "odoo_menu" in kinds:
        candidates.extend(_menus(env, query))
    if "odoo_setting" in kinds:
        candidates.extend(_settings(env, query))

    ranked = sorted(
        candidates,
        key=lambda item: (
            -_score(query, item["label"], item["description"], item.get("model")),
            _KIND_ORDER[item["kind"]],
            item["label"].casefold(),
            item.get("action_id") or item.get("view_id") or item.get("menu_id") or 0,
        ),
    )
    deduped = []
    seen = set()
    for item in ranked:
        identity = _identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return {"query": query, "references": deduped}


_KIND_ORDER = {kind: index for index, kind in enumerate(_KINDS)}


def _query(value):
    if not isinstance(value, str):
        raise RuntimeError("navigation_request_invalid")
    text = " ".join(value.split())
    if not 1 <= len(text) <= _MAX_QUERY or "\x00" in text:
        raise RuntimeError("navigation_request_invalid")
    return text


def _tokens(query):
    return tuple(re.findall(r"[\w]+", query.casefold(), flags=re.UNICODE)[:_MAX_TOKENS])


def _one_line(value, *, maximum=160, fallback=""):
    text = " ".join(str(value or "").split())
    if not text:
        text = fallback
    return text[:maximum]


def _description(value, fallback=""):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return _one_line(text, maximum=_MAX_DESCRIPTION, fallback=fallback)


def _score(query, label, description, model=None):
    needle = query.casefold()
    label_cf = label.casefold()
    description_cf = (description or "").casefold()
    model_cf = (model or "").casefold()
    score = 0
    if needle == label_cf or needle == model_cf:
        score += 100
    elif needle in label_cf:
        score += 60
    elif needle in model_cf:
        score += 50
    terms = _tokens(query)
    for term in terms:
        if term in label_cf:
            score += 20
        elif term in model_cf:
            score += 15
        elif term in description_cf:
            score += 8
    return score


def _reference(kind, label, description="", *, model=None, action_id=None, view_id=None, menu_id=None, setting_field=None):
    return {
        "kind": kind,
        "label": _one_line(label, fallback=kind),
        "description": _description(description),
        "model": model if isinstance(model, str) else None,
        "action_id": action_id if type(action_id) is int and action_id > 0 else None,
        "view_id": view_id if type(view_id) is int and view_id > 0 else None,
        "menu_id": menu_id if type(menu_id) is int and menu_id > 0 else None,
        "setting_field": setting_field if isinstance(setting_field, str) else None,
    }


def _identity(item):
    return (
        item["kind"],
        item.get("model"),
        item.get("action_id"),
        item.get("view_id"),
        item.get("menu_id"),
        item.get("setting_field"),
    )


def _readable_model(env, model, *, allow_transient=False):
    if not isinstance(model, str) or model not in env:
        return False
    if not allow_transient and not agent_model_is_eligible(env, model):
        return False
    try:
        model_set = env[model]
        if getattr(model_set, "_abstract", False):
            return False
        if getattr(model_set, "_transient", False) and not allow_transient:
            return False
        model_set.browse().check_access("read")
    except Exception:  # noqa: BLE001 - navigation discovery fails closed
        return False
    return True


def _models(env, query, limit):
    try:
        rows = search_agent_models(env, query, limit=limit)
    except Exception:  # noqa: BLE001 - one discovery source must not widen authority
        return []
    return [
        _reference(
            "odoo_model",
            row["label"],
            f"Abrir registros de {row['label']}",
            model=row["model"],
        )
        for row in rows
    ]


def _candidate_records(model, query, *, extra_domain=()):
    terms = _tokens(query)
    seen = set()
    records = model.browse()
    for term in terms or (query,):
        domain = list(extra_domain) + [("name", "ilike", term)]
        try:
            batch = model.search(domain, limit=_MAX_CANDIDATES_PER_TOKEN)
        except Exception:  # noqa: BLE001 - metadata source unavailable for this user
            continue
        new_ids = [record.id for record in batch if record.id not in seen]
        if new_ids:
            seen.update(new_ids)
            records |= model.browse(new_ids)
    return records


def _group_allowed(env, record):
    if "groups_id" not in record._fields:
        return True
    try:
        groups = record.groups_id
        return not groups or bool(groups & env.user.groups_id)
    except Exception:  # noqa: BLE001
        return False


def _action_available(env, action):
    try:
        action = action.exists()
        if not action or action.type != "ir.actions.act_window":
            return False
        action.check_access("read")
        if not _group_allowed(env, action):
            return False
        return _readable_model(
            env,
            action.res_model,
            allow_transient=action.res_model == "res.config.settings",
        )
    except Exception:  # noqa: BLE001
        return False


def _actions(env, query):
    try:
        model = env["ir.actions.act_window"]
        records = _candidate_records(model, query)
    except Exception:  # noqa: BLE001
        return []
    result = []
    for action in records:
        if not _action_available(env, action):
            continue
        label = _one_line(action.name, fallback=action.res_model)
        result.append(
            _reference(
                "odoo_action",
                label,
                f"Abrir {label} en Odoo",
                model=action.res_model,
                action_id=action.id,
            )
        )
    return result


def _views(env, query):
    try:
        model = env["ir.ui.view"]
        records = _candidate_records(model, query)
    except Exception:  # noqa: BLE001
        return []
    result = []
    for view in records:
        try:
            view = view.exists()
            model_name = view.model
            view_type = "list" if view.type == "tree" else view.type
            if (
                not view
                or view_type not in _VIEW_TYPES
                or not _group_allowed(env, view)
                or not _readable_model(env, model_name)
            ):
                continue
            view.check_access("read")
        except Exception:  # noqa: BLE001
            continue
        label = _one_line(view.name, fallback=model_name)
        result.append(
            _reference(
                "odoo_view",
                label,
                f"Abrir la vista {view_type} de {model_name}",
                model=model_name,
                view_id=view.id,
            )
        )
    return result


def _visible_menu_ids(env):
    try:
        visible = env["ir.ui.menu"]._visible_menu_ids()
    except Exception:  # noqa: BLE001
        return set()
    return {item for item in visible if type(item) is int and item > 0}


def _menus(env, query):
    visible_ids = _visible_menu_ids(env)
    if not visible_ids:
        return []
    try:
        menu_model = env["ir.ui.menu"]
        records = _candidate_records(menu_model, query, extra_domain=(("id", "in", list(visible_ids)),))
    except Exception:  # noqa: BLE001
        return []
    result = []
    for menu in records:
        if menu.id not in visible_ids:
            continue
        try:
            action = menu.action
            if not action or action._name != "ir.actions.act_window" or not _action_available(env, action):
                continue
            parent = menu.parent_id.name if menu.parent_id else ""
        except Exception:  # noqa: BLE001
            continue
        label = _one_line(menu.name, fallback=action.name)
        description = f"Menú visible en {parent}" if parent else "Menú visible de Odoo"
        result.append(
            _reference(
                "odoo_menu",
                label,
                description,
                model=action.res_model,
                action_id=action.id,
                menu_id=menu.id,
            )
        )
    return result


def _settings_actions(env):
    visible_ids = _visible_menu_ids(env)
    action_ids = []
    if visible_ids:
        try:
            menus = env["ir.ui.menu"].browse(list(visible_ids)).exists()
            for menu in menus:
                action = menu.action
                if (
                    action
                    and action._name == "ir.actions.act_window"
                    and action.res_model == "res.config.settings"
                    and _action_available(env, action)
                    and action.id not in action_ids
                ):
                    action_ids.append(action.id)
        except Exception:  # noqa: BLE001
            pass
    if action_ids:
        return env["ir.actions.act_window"].browse(action_ids)
    try:
        actions = env["ir.actions.act_window"].search(
            [("res_model", "=", "res.config.settings")], limit=8
        )
    except Exception:  # noqa: BLE001
        return env["ir.actions.act_window"].browse()
    return actions.filtered(lambda action: _action_available(env, action))


def _settings(env, query):
    if not _readable_model(env, "res.config.settings", allow_transient=True):
        return []
    actions = _settings_actions(env)
    if not actions:
        return []
    try:
        metadata = env["res.config.settings"].fields_get(
            attributes=["string", "help", "type"]
        )
    except Exception:  # noqa: BLE001
        return []
    query_cf = query.casefold()
    terms = _tokens(query)
    candidates = []
    for name, description in metadata.items():
        if not isinstance(name, str) or not isinstance(description, dict):
            continue
        label = _one_line(description.get("string"), fallback=name)
        help_text = _description(description.get("help"))
        searchable = f"{name} {label} {help_text}".casefold()
        if query_cf not in searchable and terms and not all(term in searchable for term in terms):
            continue
        candidates.append((name, label, help_text))
        if len(candidates) >= _MAX_CANDIDATES_PER_TOKEN:
            break
    if not candidates:
        return []
    action = actions[0]
    return [
        _reference(
            "odoo_setting",
            label,
            help_text or f"Opción instalada de Configuración: {label}",
            model="res.config.settings",
            action_id=action.id,
            setting_field=name,
        )
        for name, label, help_text in candidates
    ]
