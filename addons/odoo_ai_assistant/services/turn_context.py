"""Current Odoo ACL/schema helpers used by embedded capabilities."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Protocol

QUERY_FIELD_PRIORITY = (
    "id",
    "name",
    "ref",
    "state",
    "active",
    "company_id",
    "partner_id",
    "user_id",
    "currency_id",
    "date",
    "create_date",
    "write_date",
    "amount_total",
    "amount_untaxed",
    "amount_tax",
    "amount_residual",
    "amount_residual_signed",
    "invoice_date",
    "invoice_date_due",
    "invoice_payment_term_id",
    "payment_state",
    "move_type",
    "journal_id",
    "display_name",
)
QUERY_ALLOWED_FIELD_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "html",
        "integer",
        "many2one",
        "monetary",
        "selection",
        "text",
    }
)
ACTION_PREVIEW_ALLOWED_FIELD_TYPES = frozenset(
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
        "text",
    }
)
ACTION_PREVIEW_BLOCKED_FIELDS = frozenset(
    {
        "__last_update",
        "company_id",
        "company_ids",
        "create_date",
        "create_uid",
        "groups_id",
        "id",
        "password",
        "password_crypt",
        "share",
        "write_date",
        "write_uid",
    }
)
_SENSITIVE_FIELD_PARTS = ("api_key", "credential", "password", "secret", "token")
QUERY_SENSITIVE_FIELD_PARTS = (*_SENSITIVE_FIELD_PARTS, "private_key")
AGENT_BLOCKED_MODELS = frozenset(
    {
        "base.automation",
        "ir.config_parameter",
        "ir.cron",
        "ir.model",
        "ir.model.access",
        "ir.model.fields",
        "ir.rule",
        "res.groups",
        "res.users",
    }
)
AGENT_BLOCKED_MODEL_PREFIXES = ("auth.", "ir.actions.", "ir.ui.")


class _Registry(Protocol):
    models: object


class OdooEnvironment(Protocol):
    registry: _Registry

    def __contains__(self, model: object) -> bool: ...

    def __getitem__(self, model: str): ...


class TurnContextError(RuntimeError):
    """Sanitized ACL/schema discovery failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def visible_query_fields(env: OdooEnvironment, model: str) -> tuple[str, ...]:
    """Return bounded readable scalar fields under the effective Odoo user."""

    try:
        model_set = env[model]
        model_set.browse().check_access("read")
        descriptions = model_set.fields_get(attributes=["type"])
    except Exception:  # noqa: BLE001 - fail closed at the Odoo ACL boundary
        raise TurnContextError("access_denied") from None
    if not isinstance(descriptions, dict):
        raise TurnContextError("access_denied")

    allowed = [
        name
        for name, description in descriptions.items()
        if isinstance(name, str)
        and isinstance(description, dict)
        and description.get("type") in QUERY_ALLOWED_FIELD_TYPES
        and not any(part in name.casefold() for part in QUERY_SENSITIVE_FIELD_PARTS)
    ]
    unique = set(allowed)
    priority = [name for name in QUERY_FIELD_PRIORITY if name in unique]
    selected = (priority + sorted(unique - set(priority)))[:64]
    ordered = tuple(sorted(selected, key=lambda item: (item != "id", item)))
    if not ordered:
        raise TurnContextError("access_denied")
    return ordered


def visible_action_preview_fields(
    env: OdooEnvironment,
    model: str,
) -> tuple[str, ...]:
    """Return bounded writable scalar fields without increasing field authority."""

    try:
        model_set = env[model]
        model_set.browse().check_access("read")
        descriptions = model_set.fields_get(attributes=["readonly", "type"])
    except Exception:  # noqa: BLE001 - fail closed at the Odoo ACL boundary
        raise TurnContextError("access_denied") from None
    if not isinstance(descriptions, dict):
        raise TurnContextError("access_denied")

    candidates = sorted(
        name
        for name, description in descriptions.items()
        if isinstance(name, str)
        and isinstance(description, dict)
        and description.get("readonly") is False
        and description.get("type") in ACTION_PREVIEW_ALLOWED_FIELD_TYPES
        and _action_preview_field_permitted(name)
    )[:64]
    allowed: list[str] = []
    for name in candidates:
        try:
            model_set.check_field_access_rights("write", [name])
        except Exception:  # noqa: BLE001,S112 - inaccessible fields are omitted
            continue
        allowed.append(name)
    if not allowed:
        raise TurnContextError("access_denied")
    return tuple(allowed)


def agent_model_is_eligible(env: OdooEnvironment, model: object) -> bool:
    """Check whether one runtime model may be exposed to embedded capabilities."""

    if (
        not isinstance(model, str)
        or re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$", model) is None
        or model in AGENT_BLOCKED_MODELS
        or model.startswith(AGENT_BLOCKED_MODEL_PREFIXES)
        or model not in env
    ):
        return False
    try:
        model_set = env[model]
        if getattr(model_set, "_abstract", False) or getattr(model_set, "_transient", False):
            return False
        model_set.browse().check_access("read")
    except Exception:  # noqa: BLE001 - eligibility is fail closed
        return False
    return True


def search_agent_models(
    env: OdooEnvironment,
    query: object,
    *,
    limit: object,
) -> list[dict[str, str]]:
    """Search eligible runtime models without granting technical-model access."""

    if (
        not isinstance(query, str)
        or not 1 <= len(query.strip()) <= 128
        or type(limit) is not int
        or not 1 <= limit <= 32
    ):
        raise TurnContextError("invalid_request")
    terms = _search_terms(query)
    if not terms:
        raise TurnContextError("invalid_request")
    try:
        registry_models = tuple(env.registry.models)
    except Exception:  # noqa: BLE001 - sanitize registry discovery
        raise TurnContextError("model_catalog_unavailable") from None

    matches: list[tuple[tuple[int, int, str], str, str]] = []
    for model in registry_models:
        if not isinstance(model, str):
            continue
        description = _safe_model_label(getattr(env[model], "_description", model), model)
        rank = _model_search_rank(terms, model=model, label=description)
        if rank is None:
            continue
        matches.append((rank, model, description))

    result = []
    for _rank, model, label in sorted(matches):
        if not agent_model_is_eligible(env, model):
            continue
        result.append({"label": label, "model": model})
        if len(result) >= limit:
            break
    return result


def _search_terms(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return tuple(token for token in re.findall(r"[^\W_]+", without_marks) if token)


def _model_search_rank(
    query_terms: tuple[str, ...],
    *,
    model: str,
    label: str,
) -> tuple[int, int, str] | None:
    """Rank lexical and close morphological matches without a business alias table."""

    model_terms = _search_terms(model.replace(".", " "))
    label_terms = _search_terms(label)
    candidate_terms = (*model_terms, *label_terms)
    if not candidate_terms:
        return None

    query_phrase = " ".join(query_terms)
    model_phrase = " ".join(model_terms)
    label_phrase = " ".join(label_terms)
    if query_phrase in {model_phrase, label_phrase}:
        return (0, 0, model)
    if all(term in candidate_terms for term in query_terms):
        return (1, 0, model)

    similarities = [
        max(SequenceMatcher(None, term, candidate).ratio() for candidate in candidate_terms)
        for term in query_terms
    ]
    thresholds = [0.82 if len(term) <= 4 else 0.72 for term in query_terms]
    if any(similarity < threshold for similarity, threshold in zip(similarities, thresholds)):
        return None
    distance = round(sum(1.0 - similarity for similarity in similarities) * 10_000)
    return (2, distance, model)


def _safe_model_label(value: object, fallback: str) -> str:
    label = " ".join(str(value).split())[:240]
    if not label or any(ord(character) < 32 for character in label):
        return fallback
    return label


def _action_preview_field_permitted(field: str) -> bool:
    normalized = field.casefold()
    return field not in ACTION_PREVIEW_BLOCKED_FIELDS and not any(
        part in normalized for part in _SENSITIVE_FIELD_PARTS
    )
