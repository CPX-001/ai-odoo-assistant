"""Public product-profile mapping over the internal technical-access seam.

The current runtime may retain historical BUSINESS/DEVELOPER enum names for
compatibility. Product-facing projections use exactly User or Technical. This
mapping grants no permission; effective Odoo ACLs and policy remain authoritative.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ProductUserProfile(StrEnum):
    USER = "user"
    TECHNICAL = "technical"


_TECHNICAL_VALUES = {
    "technical",
    "developer",
    "operator",
    "admin",
    "system",
}


def product_profile_from_technical(value: Any) -> ProductUserProfile:
    """Map internal compatibility values to the two public product profiles."""

    candidate = getattr(value, "value", value)
    normalized = str(candidate or "").strip().casefold()
    if normalized in _TECHNICAL_VALUES:
        return ProductUserProfile.TECHNICAL
    return ProductUserProfile.USER


def product_profile_for_env(env) -> ProductUserProfile:
    """Project the Odoo user's profile without creating execution authority."""

    user = getattr(env, "user", None)
    try:
        if user is not None and user.has_group("base.group_system"):
            return ProductUserProfile.TECHNICAL
    except Exception:  # noqa: BLE001 - profile detection fails closed
        return ProductUserProfile.USER
    return ProductUserProfile.USER


__all__ = [
    "ProductUserProfile",
    "product_profile_for_env",
    "product_profile_from_technical",
]
