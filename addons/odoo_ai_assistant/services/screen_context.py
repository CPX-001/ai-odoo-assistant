"""Strict validation and bounded enrichment of Assistant screen context."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from lxml import etree

MAX_ODOO_ID: Final = 2_147_483_647
MAX_SELECTED_IDS: Final = 8
MAX_SCREEN_AGE_SECONDS: Final = 300
MAX_FUTURE_SKEW_SECONDS: Final = 30
MAX_VIEW_FIELDS: Final = 16
MAX_VIEW_LABELS: Final = 8
ALLOWED_VIEW_TYPES: Final = frozenset(
    {"activity", "calendar", "form", "graph", "kanban", "list", "pivot"}
)
ALLOWED_CONTEXT_KEYS: Final = frozenset({"active_id", "active_ids", "active_model"})
SCREEN_KEYS: Final = frozenset(
    {
        "action_id",
        "allowed_context_subset",
        "captured_at",
        "menu_id",
        "model",
        "res_id",
        "selected_ids",
        "view_id",
        "view_type",
    }
)
IDENTITY_KEYS: Final = frozenset(
    {"allowed_company_ids", "company_id", "companies", "lang", "uid", "user_id"}
)

ContextHint = str | int | list[int]
ScreenValue = str | int | list[int] | dict[str, ContextHint] | None
_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class ScreenContextValidationError(ValueError):
    """Sanitized rejection of browser-provided navigation data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ValidatedScreenContext:
    """Bounded navigation data; still a hint and never identity authority."""

    action_id: int | None
    menu_id: int | None
    view_id: int | None
    view_type: str | None
    model: str | None
    res_id: int | None
    selected_ids: tuple[int, ...]
    allowed_context_subset: dict[str, ContextHint]
    captured_at: datetime

    def to_mapping(self) -> dict[str, ScreenValue]:
        return {
            "action_id": self.action_id,
            "allowed_context_subset": dict(self.allowed_context_subset),
            "captured_at": self.captured_at.isoformat().replace("+00:00", "Z"),
            "menu_id": self.menu_id,
            "model": self.model,
            "res_id": self.res_id,
            "selected_ids": list(self.selected_ids),
            "view_id": self.view_id,
            "view_type": self.view_type,
        }


def validate_query_screen(
    payload: Mapping[str, object],
    *,
    clock: Callable[[], datetime] | None = None,
) -> ValidatedScreenContext:
    """Validate embedded-agent context; both the current model and record are optional."""

    return _validate_screen(
        payload,
        clock=clock,
        require_record=False,
        require_model=False,
    )


def enrich_runtime_screen(env, screen: Mapping[str, object]) -> dict[str, object]:
    """Add current-user semantic view facts without turning screen hints into authority.

    The browser-provided model/view identifiers have already passed the enqueue contract. This
    function re-resolves them against the effective non-sudo Environment and only contributes
    bounded labels from the *resolved* Odoo model/view. It deliberately omits raw XML, domains,
    button method names and other executable/technical details.
    """

    if not isinstance(screen, Mapping):
        return {}
    result = dict(screen)
    model = screen.get("model")
    if not isinstance(model, str) or _MODEL_PATTERN.fullmatch(model) is None:
        return result
    try:
        model_set = env[model]
        model_set.browse().check_access("read")
    except Exception:  # noqa: BLE001 - screen enrichment is non-authoritative and fail-soft
        return result

    model_label = _one_line(getattr(model_set, "_description", ""), maximum=160)
    translator = getattr(env, "_", None)
    if model_label and callable(translator):
        try:
            model_label = _one_line(translator(model_label), maximum=160) or model_label
        except Exception:  # noqa: BLE001 - localization must not affect the turn
            pass
    if model_label:
        result["model_label"] = model_label
    model_module = getattr(model_set, "_module", None)
    if isinstance(model_module, str) and _MODULE_PATTERN.fullmatch(model_module):
        result["model_module"] = model_module

    view_id = screen.get("view_id")
    view_type = screen.get("view_type")
    if type(view_id) is not int or view_id <= 0 or view_type not in ALLOWED_VIEW_TYPES:
        return result

    try:
        resolved = model_set.get_view(view_id=view_id, view_type=view_type)
    except Exception:  # noqa: BLE001 - inaccessible/invalid views simply contribute no detail
        return result
    if not isinstance(resolved, Mapping):
        return result
    resolved_model = resolved.get("model")
    if isinstance(resolved_model, str) and resolved_model != model:
        return result
    resolved_id = resolved.get("id")
    if type(resolved_id) is int and resolved_id > 0 and resolved_id != view_id:
        return result

    _enrich_view_identity(env, result, model=model, view_id=view_id, view_type=view_type)
    arch = resolved.get("arch")
    if not isinstance(arch, str) or not arch.strip() or len(arch) > 512 * 1024:
        return result
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
        root = etree.fromstring(arch.encode("utf-8"), parser=parser)
    except (ValueError, etree.XMLSyntaxError):
        return result

    field_names = _view_field_names(root)
    if field_names:
        try:
            descriptions = model_set.fields_get(
                allfields=list(field_names),
                attributes=["string"],
            )
        except Exception:  # noqa: BLE001 - field labels are presentation context only
            descriptions = {}
        labels = []
        if isinstance(descriptions, Mapping):
            for name in field_names:
                description = descriptions.get(name)
                label = (
                    _one_line(description.get("string"), maximum=120)
                    if isinstance(description, Mapping)
                    else ""
                )
                if label and label not in labels:
                    labels.append(label)
        if labels:
            result["view_fields"] = labels[:MAX_VIEW_FIELDS]

    actions = _xml_string_labels(root, "button", maximum=MAX_VIEW_LABELS)
    if actions:
        result["view_actions"] = actions
    sections = _xml_string_labels(root, "page", maximum=MAX_VIEW_LABELS)
    if sections:
        result["view_sections"] = sections
    return result


def _enrich_view_identity(env, result, *, model, view_id, view_type):
    try:
        view = env["ir.ui.view"].browse(view_id).exists()
        if not view:
            return
        row = view.read(["key", "model", "name", "type"], load=None)[0]
    except Exception:  # noqa: BLE001 - get_view remains the primary revalidation boundary
        return
    if row.get("model") != model or row.get("type") != view_type:
        return
    label = _one_line(row.get("name"), maximum=160)
    if label:
        result["view_label"] = label
    key = _one_line(row.get("key"), maximum=160)
    if key and re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", key):
        result["view_key"] = key
        module = key.partition(".")[0]
        if _MODULE_PATTERN.fullmatch(module):
            result["view_module"] = module


def _view_field_names(root) -> tuple[str, ...]:
    names = []
    for node in root.iter("field"):
        name = node.get("name")
        if (
            isinstance(name, str)
            and _FIELD_PATTERN.fullmatch(name)
            and name not in names
        ):
            names.append(name)
        if len(names) >= MAX_VIEW_FIELDS:
            break
    return tuple(names)


def _xml_string_labels(root, tag: str, *, maximum: int) -> list[str]:
    labels = []
    for node in root.iter(tag):
        label = _one_line(node.get("string"), maximum=120)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= maximum:
            break
    return labels


def _one_line(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    if not normalized or "\x00" in normalized:
        return ""
    return normalized[:maximum]


def _validate_screen(
    payload: Mapping[str, object],
    *,
    clock: Callable[[], datetime] | None,
    require_record: bool,
    require_model: bool = True,
) -> ValidatedScreenContext:
    if not isinstance(payload, Mapping):
        raise ScreenContextValidationError("invalid_screen")
    unexpected = set(payload) - SCREEN_KEYS
    if unexpected:
        code = "identity_not_allowed" if unexpected & IDENTITY_KEYS else "unexpected_screen_key"
        raise ScreenContextValidationError(code)

    model = (
        _model_name(payload.get("model"))
        if require_model or payload.get("model") is not None
        else None
    )
    res_id = (
        _positive_id(payload.get("res_id"))
        if require_record
        else _optional_positive_id(payload.get("res_id"))
    )
    selected_ids = _positive_id_list(payload.get("selected_ids", []), maximum=MAX_SELECTED_IDS)
    captured_at = _captured_at(payload.get("captured_at"))
    now = (clock or _utc_now)()
    if now.tzinfo is None:
        raise ScreenContextValidationError("clock_unavailable")
    now = now.astimezone(UTC)
    if captured_at < now - timedelta(seconds=MAX_SCREEN_AGE_SECONDS):
        raise ScreenContextValidationError("screen_expired")
    if captured_at > now + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise ScreenContextValidationError("screen_from_future")

    view_type = payload.get("view_type")
    if view_type is not None and (
        not isinstance(view_type, str) or view_type not in ALLOWED_VIEW_TYPES
    ):
        raise ScreenContextValidationError("invalid_view_type")

    return ValidatedScreenContext(
        action_id=_optional_positive_id(payload.get("action_id")),
        menu_id=_optional_positive_id(payload.get("menu_id")),
        view_id=_optional_positive_id(payload.get("view_id")),
        view_type=view_type,
        model=model,
        res_id=res_id,
        selected_ids=selected_ids,
        allowed_context_subset=_context_subset(
            payload.get("allowed_context_subset", {}), model=model, res_id=res_id
        ),
        captured_at=captured_at,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_name(value: object) -> str:
    if not isinstance(value, str) or not _MODEL_PATTERN.fullmatch(value):
        raise ScreenContextValidationError("invalid_model")
    return value


def _positive_id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_ODOO_ID:
        raise ScreenContextValidationError("invalid_record_id")
    return value


def _optional_positive_id(value: object) -> int | None:
    if value is None:
        return None
    return _positive_id(value)


def _positive_id_list(value: object, *, maximum: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ScreenContextValidationError("invalid_selected_ids")
    try:
        parsed = tuple(_positive_id(item) for item in value)
    except ScreenContextValidationError as error:
        raise ScreenContextValidationError("invalid_selected_ids") from error
    if len(parsed) != len(set(parsed)):
        raise ScreenContextValidationError("invalid_selected_ids")
    return parsed


def _captured_at(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and len(value) <= 40:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ScreenContextValidationError("invalid_captured_at") from None
    else:
        raise ScreenContextValidationError("invalid_captured_at")
    if parsed.tzinfo is None:
        raise ScreenContextValidationError("invalid_captured_at")
    return parsed.astimezone(UTC)


def _context_subset(
    value: object, *, model: str | None, res_id: int | None
) -> dict[str, ContextHint]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ScreenContextValidationError("invalid_context_subset")
    keys = set(value)
    if keys - ALLOWED_CONTEXT_KEYS:
        raise ScreenContextValidationError("context_key_not_allowed")

    result: dict[str, ContextHint] = {}
    if "active_model" in value:
        active_model = value["active_model"]
        if active_model != model or model is None:
            raise ScreenContextValidationError("inconsistent_context_hint")
        result["active_model"] = model
    if "active_id" in value:
        active_id = _positive_id(value["active_id"])
        if res_id is None or active_id != res_id:
            raise ScreenContextValidationError("inconsistent_context_hint")
        result["active_id"] = active_id
    if "active_ids" in value:
        active_ids = _positive_id_list(value["active_ids"], maximum=MAX_SELECTED_IDS)
        result["active_ids"] = list(active_ids)
    return result