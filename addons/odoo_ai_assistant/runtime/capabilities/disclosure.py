"""Progressive-disclosure state derivation for effective capability catalogs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import CapabilityError
from .skills import selector_matches


@dataclass(frozen=True, slots=True)
class DisclosurePolicy:
    """Disclosure is disabled by default until evals justify lazy schemas."""

    enabled: bool = False
    eager_selectors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityDisclosureSnapshot:
    available: tuple[str, ...]
    revealed: tuple[str, ...]
    active: tuple[str, ...]

    def __post_init__(self) -> None:
        available = set(self.available)
        revealed = set(self.revealed)
        active = set(self.active)
        if not revealed <= available or not active <= revealed:
            raise CapabilityError("capability_disclosure_state_invalid")


def build_disclosure_snapshot(
    available_names: Iterable[str],
    *,
    policy: DisclosurePolicy | None = None,
    requested_selectors: Iterable[str] = (),
    active_names: Iterable[str] = (),
) -> CapabilityDisclosureSnapshot:
    available = tuple(sorted(set(available_names)))
    available_set = set(available)
    active = set(active_names)
    if not active <= available_set:
        raise CapabilityError("capability_disclosure_state_invalid")
    policy = policy or DisclosurePolicy()
    if not policy.enabled:
        revealed = set(available)
    else:
        selectors = tuple(policy.eager_selectors) + tuple(requested_selectors)
        revealed = {
            name
            for name in available
            if any(selector_matches(selector, name) for selector in selectors)
        }
        revealed.update(active)
    return CapabilityDisclosureSnapshot(
        available=available,
        revealed=tuple(sorted(revealed)),
        active=tuple(sorted(active)),
    )


__all__ = [
    "CapabilityDisclosureSnapshot",
    "DisclosurePolicy",
    "build_disclosure_snapshot",
]
