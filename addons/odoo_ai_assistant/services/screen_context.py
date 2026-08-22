"""Strict validation of untrusted browser navigation hints."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

MAX_ODOO_ID: Final = 2_147_483_647
MAX_SELECTED_IDS: Final = 8
MAX_SCREEN_AGE_SECONDS: Final = 300
MAX_FUTURE_SKEW_SECONDS: Final = 30
ALLOWED_VIEW_TYPES: Final = frozenset(
    {"activity", "calendar", "form", "graph", "kanban", "list", "pivot"}
)
ALLOWED_CONTEXT_KEYS: Final = frozenset(
    {"active_id", "active_ids", "active_model"}
)
SCREEN_KEYS: Final = frozenset(
    {
        "action_id",
        "allowed_context_subset",
        "captured_at",
        "menu_id",
        "model",
        "res_id",
        "selected_ids",
        "view_type",
    }
)
IDENTITY_KEYS: Final = frozenset(
    {
        "allowed_company_ids",
        "company_id",
        "companies",
        "lang",
        "uid",
        "user_id",
    }
)

ContextHint = str | int | list[int]
ScreenValue = str | int | list[int] | dict[str, ContextHint] | None
_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


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
    view_type: str | None
    model: str
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
            "view_type": self.view_type,
        }


def validate_context_read_screen(
    payload: Mapping[str, object],
    *,
    clock: Callable[[], datetime] | None = None,
) -> ValidatedScreenContext:
    """Validate the single-current-record ScreenContext supported in M2."""

    return _validate_screen(payload, clock=clock, require_record=True)


def validate_query_screen(
    payload: Mapping[str, object],
    *,
    clock: Callable[[], datetime] | None = None,
) -> ValidatedScreenContext:
    """Validate model-scoped QUERY context; a current record is optional."""

    return _validate_screen(payload, clock=clock, require_record=False)


def _validate_screen(
    payload: Mapping[str, object],
    *,
    clock: Callable[[], datetime] | None,
    require_record: bool,
) -> ValidatedScreenContext:
    if not isinstance(payload, Mapping):
        raise ScreenContextValidationError("invalid_screen")
    unexpected = set(payload) - SCREEN_KEYS
    if unexpected:
        code = "identity_not_allowed" if unexpected & IDENTITY_KEYS else "unexpected_screen_key"
        raise ScreenContextValidationError(code)

    model = _model_name(payload.get("model"))
    res_id = (
        _positive_id(payload.get("res_id"))
        if require_record
        else _optional_positive_id(payload.get("res_id"))
    )
    selected_ids = _positive_id_list(
        payload.get("selected_ids", []), maximum=MAX_SELECTED_IDS
    )
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
    value: object, *, model: str, res_id: int | None
) -> dict[str, ContextHint]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ScreenContextValidationError("invalid_context_subset")
    keys = set(value)
    if keys - ALLOWED_CONTEXT_KEYS:
        raise ScreenContextValidationError("context_key_not_allowed")

    result: dict[str, ContextHint] = {}
    if "active_model" in value:
        active_model = value["active_model"]
        if active_model != model:
            raise ScreenContextValidationError("inconsistent_context_hint")
        result["active_model"] = model
    if "active_id" in value:
        active_id = _positive_id(value["active_id"])
        if res_id is None or active_id != res_id:
            raise ScreenContextValidationError("inconsistent_context_hint")
        result["active_id"] = active_id
    if "active_ids" in value:
        active_ids = _positive_id_list(
            value["active_ids"], maximum=MAX_SELECTED_IDS
        )
        result["active_ids"] = list(active_ids)
    return result
