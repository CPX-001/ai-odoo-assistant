"""Per-coroutine delivery channel for provider-neutral agent answer deltas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token

AgentDeltaSink = Callable[[str], Awaitable[None] | None]

_AGENT_DELTA_SINK: ContextVar[AgentDeltaSink | None] = ContextVar(
    "odoo_ai_agent_delta_sink",
    default=None,
)


def bind_agent_delta_sink(sink: AgentDeltaSink) -> Token[AgentDeltaSink | None]:
    """Bind a stream consumer to only the current async context."""

    return _AGENT_DELTA_SINK.set(sink)


def reset_agent_delta_sink(token: Token[AgentDeltaSink | None]) -> None:
    _AGENT_DELTA_SINK.reset(token)


def current_agent_delta_sink() -> AgentDeltaSink | None:
    return _AGENT_DELTA_SINK.get()
