"""Streaming-aware Codex completion loop for the unified agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from odoo_ai.adapters.codex_engine import (
    CodexEngineError,
    _enforce_notification_policy,
    _handle_dynamic_tool_request,
    _reject_forbidden_completed_item,
    _remaining_seconds,
    _sanitized_turn_error_code,
    _server_request_id,
)
from odoo_ai.adapters.codex_runtime import CodexAppServerClient
from odoo_ai.tools import ToolExecutor

RawDeltaSink = Callable[[str], Awaitable[None]]


async def wait_for_completion_with_deltas(
    client: CodexAppServerClient,
    *,
    thread_id: str,
    turn_id: str,
    executor: ToolExecutor | None,
    dynamic_tool_names: Mapping[str, str],
    deadline: float,
    max_events: int,
    raw_delta_sink: RawDeltaSink,
) -> tuple[dict[str, object], frozenset[str]]:
    """Mirror the bounded host loop while surfacing only validated agent-message deltas."""

    dynamic_call_ids: set[str] = set()
    request_ids: set[tuple[type[object], object]] = set()
    for _ in range(max_events):
        event = await client.next_event(timeout_seconds=_remaining_seconds(deadline))
        method = event.get("method")
        params = event.get("params")
        if "id" in event:
            request_id = _server_request_id(event.get("id"))
            request_key = (type(request_id), request_id)
            if request_key in request_ids:
                raise CodexEngineError("codex_server_request_duplicate")
            request_ids.add(request_key)
            call_id = await _handle_dynamic_tool_request(
                client,
                event,
                thread_id=thread_id,
                turn_id=turn_id,
                executor=executor,
                dynamic_tool_names=dynamic_tool_names,
            )
            dynamic_call_ids.add(call_id)
            continue
        if not isinstance(method, str):
            raise CodexEngineError("codex_event_invalid")
        _enforce_notification_policy(
            method,
            params,
            thread_id=thread_id,
            turn_id=turn_id,
        )
        if method == "item/agentMessage/delta":
            delta = _validated_agent_message_delta(
                params,
                thread_id=thread_id,
                turn_id=turn_id,
            )
            if delta:
                await raw_delta_sink(delta)
            continue
        if method == "item/completed":
            _reject_forbidden_completed_item(
                params,
                thread_id=thread_id,
                turn_id=turn_id,
                dynamic_call_ids=dynamic_call_ids,
            )
            continue
        if method != "turn/completed":
            continue
        if not isinstance(params, dict):
            raise CodexEngineError("codex_turn_completion_invalid")
        if params.get("threadId") != thread_id or not isinstance(params.get("turn"), dict):
            raise CodexEngineError("codex_turn_completion_mismatch")
        turn = cast(dict[str, object], params["turn"])
        if turn.get("id") != turn_id:
            raise CodexEngineError("codex_turn_completion_mismatch")
        status = turn.get("status")
        if status == "interrupted":
            raise CodexEngineError("codex_turn_interrupted")
        if status != "completed" or turn.get("error") not in (None, {}):
            raise CodexEngineError(_sanitized_turn_error_code(turn.get("error")))
        return turn, frozenset(dynamic_call_ids)
    raise CodexEngineError("codex_event_budget_exceeded")


def _validated_agent_message_delta(
    params: object,
    *,
    thread_id: str,
    turn_id: str,
) -> str:
    if not isinstance(params, dict) or set(params) != {
        "delta",
        "itemId",
        "threadId",
        "turnId",
    }:
        raise CodexEngineError("codex_agent_delta_invalid")
    item_id = params.get("itemId")
    delta = params.get("delta")
    if (
        params.get("threadId") != thread_id
        or params.get("turnId") != turn_id
        or not isinstance(item_id, str)
        or not 1 <= len(item_id) <= 256
        or not isinstance(delta, str)
        or len(delta.encode("utf-8")) > 256 * 1024
    ):
        raise CodexEngineError("codex_agent_delta_invalid")
    return delta
