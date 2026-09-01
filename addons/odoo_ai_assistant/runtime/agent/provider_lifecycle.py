"""Best-effort provider session lifecycle around the host-owned decision loop."""

from __future__ import annotations

import inspect
from typing import Protocol, runtime_checkable

from . import service

_INSTALLED = False
_BASE_RUN_DECISION_LOOP = service.AgentTurnService._run_decision_loop


@runtime_checkable
class ClosableReasoningProvider(Protocol):
    async def aclose(self) -> None: ...


async def close_reasoning_provider(provider) -> None:
    """Close the first concrete lifecycle owner under provider-neutral wrappers.

    Existing host wrappers compose through ``_provider``. They do not own transport resources, so
    the traversal stops at the first object exposing ``aclose``. Cleanup is deliberately
    best-effort: a provider shutdown problem must not rewrite an already-authoritative Odoo result.
    """

    current = provider
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        close = getattr(current, "aclose", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001 - cleanup cannot become business authority
                pass
            return
        current = getattr(current, "_provider", None)


async def _run_decision_loop_with_lifecycle(self, *args, **kwargs):
    try:
        return await _BASE_RUN_DECISION_LOOP(self, *args, **kwargs)
    finally:
        await close_reasoning_provider(self._decision_engine)


def install_provider_lifecycle() -> None:
    """Install one generic close boundary without coupling AgentTurnService to Codex."""

    global _INSTALLED
    if _INSTALLED:
        return
    service.AgentTurnService._run_decision_loop = _run_decision_loop_with_lifecycle
    _INSTALLED = True


__all__ = ["ClosableReasoningProvider", "close_reasoning_provider", "install_provider_lifecycle"]
