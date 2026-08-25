"""Lightweight sanitized timing for the unified agent hot path."""

from __future__ import annotations

import logging
from time import monotonic

from odoo_ai.tools import ToolCall, ToolExecutor, ValidatedToolResult

LOGGER = logging.getLogger(__name__)


def log_agent_timing(phase: str, started: float, **attributes: str) -> None:
    """Log bounded phase metadata without user content, payloads, paths, or secrets."""

    suffix = "".join(f" {key}={value}" for key, value in sorted(attributes.items()))
    LOGGER.info(
        "agent_turn_timing phase=%s duration_ms=%d%s",
        phase,
        max(0, round((monotonic() - started) * 1000)),
        suffix,
    )


class TimedToolExecutor(ToolExecutor):
    """Keep ToolExecutor semantics while recording tool-name level latency."""

    async def execute(self, call: ToolCall) -> ValidatedToolResult:
        started = monotonic()
        try:
            return await super().execute(call)
        finally:
            log_agent_timing("tool_call", started, tool=call.tool_name)
