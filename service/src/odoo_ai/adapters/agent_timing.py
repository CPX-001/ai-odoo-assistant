"""Lightweight sanitized timing for the unified agent hot path."""

from __future__ import annotations

import json
import logging
from time import monotonic

from odoo_ai.contracts import TurnLimits
from odoo_ai.tools import (
    EvidenceLedger,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolRegistry,
    ValidatedToolResult,
)

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
    """Time tools and reuse exact successful calls while preconditions are unchanged."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        ledger: EvidenceLedger,
        turn_limits: TurnLimits,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        super().__init__(
            registry=registry,
            ledger=ledger,
            turn_limits=turn_limits,
            limits=limits,
        )
        self._timed_result_cache: dict[
            tuple[str, bytes], tuple[int, ValidatedToolResult]
        ] = {}
        self._timed_call_ids: set[str] = set()

    async def execute(self, call: ToolCall) -> ValidatedToolResult:
        started = monotonic()
        if call.call_id in self._timed_call_ids:
            error = ToolExecutorError("tool_call_duplicate")
            log_agent_timing(
                "tool_call",
                started,
                tool=call.tool_name,
                status="error",
                error=error.code,
            )
            raise error
        self._timed_call_ids.add(call.call_id)

        cache_key = _semantic_cache_key(call)
        if cache_key is not None:
            cached = self._timed_result_cache.get(cache_key)
            if cached is not None and cached[0] == self._semantic_revision:
                previous = cached[1]
                result = ValidatedToolResult(
                    call_id=call.call_id,
                    tool_name=previous.tool_name,
                    data=previous.data,
                    evidence=previous.evidence,
                )
                # A host-validated cache hit has the same anti-loop semantics as a fresh
                # successful tool execution. Do not let unrelated prior failures accumulate
                # into a false consecutive-failure limit.
                self._consecutive_failures = 0
                log_agent_timing(
                    "tool_call",
                    started,
                    tool=call.tool_name,
                    status="cache_hit",
                )
                return result

        try:
            result = await super().execute(call)
        except ToolExecutorError as error:
            log_agent_timing(
                "tool_call",
                started,
                tool=call.tool_name,
                status="error",
                error=error.code,
            )
            raise
        if cache_key is not None:
            self._timed_result_cache[cache_key] = (self._semantic_revision, result)
        log_agent_timing("tool_call", started, tool=call.tool_name, status="ok")
        return result


def _semantic_cache_key(call: ToolCall) -> tuple[str, bytes] | None:
    try:
        payload = json.dumps(
            call.arguments,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return call.tool_name, payload
