"""Phase 4 Codex answer-delta integration without changing host authority.

The provider still returns one validated ``NextDecision``. This adapter only projects the
user-facing ``final_answer.answer`` field from App Server deltas into the existing host event sink.
"""

from __future__ import annotations

import asyncio

from .answer_stream import AnswerStreamError, StructuredFinalAnswerDeltaExtractor
from .codex_decision import (
    CodexAgentError,
    CodexDecisionEngine as _BaseCodexDecisionEngine,
    _CodexClient,
    _DECISION_INSTRUCTIONS,
    _MAX_EVENTS,
    _best_effort_interrupt,
    _codex_next_decision_schema,
    _decision_result,
    _decision_terminal_error,
    _decision_turn_input,
    _remaining,
    _thread_id,
    _turn_id,
    _validate_completed_item,
    _validate_decision_error_event,
    _validate_decision_notification,
    _with_completed_agent_messages,
)
from .decision_validation import validate_next_decision

_MAX_PROVIDER_DELTA = 16 * 1024
_MAX_ITEM_ID = 256


class StreamingCodexDecisionEngine(_BaseCodexDecisionEngine):
    """Current Codex decision adapter with safe provisional answer projection."""

    async def next_decision(
        self,
        *,
        message,
        conversation_summary,
        context,
        reasoning_capabilities,
        planning_capabilities,
        working_items=(),
        remaining_budgets=None,
    ):
        if self._cancelled():
            raise CodexAgentError("agent_cancelled")
        turn_input = _decision_turn_input(
            message=message,
            conversation_summary=conversation_summary,
            context=context,
            reasoning=reasoning_capabilities,
            planning=planning_capabilities,
            working_items=working_items,
            remaining_budgets=remaining_budgets or {},
        )
        client = await _CodexClient.start(self._settings)
        async with client:
            deadline = asyncio.get_running_loop().time() + self._settings.turn_timeout_seconds
            thread_result = await client.request(
                "thread/start",
                {
                    "approvalPolicy": "never",
                    "cwd": str(client.cwd),
                    "dynamicTools": [],
                    "environments": [],
                    "ephemeral": True,
                    "runtimeWorkspaceRoots": [],
                    "sandbox": "read-only",
                    **({"model": self._settings.model} if self._settings.model else {}),
                    "baseInstructions": _DECISION_INSTRUCTIONS,
                },
                timeout=_remaining(deadline),
            )
            thread_id = _thread_id(thread_result)
            turn_result = await client.request(
                "turn/start",
                {
                    "input": [{"type": "text", "text": turn_input}],
                    "outputSchema": _codex_next_decision_schema(),
                    "threadId": thread_id,
                },
                timeout=_remaining(deadline),
            )
            turn_id = _turn_id(turn_result)
            completed = await self._wait_for_completion_streaming(
                client,
                thread_id=thread_id,
                turn_id=turn_id,
                deadline=deadline,
                context=context,
            )
        return validate_next_decision(
            _decision_result(completed),
            reasoning_capabilities=reasoning_capabilities,
            planning_capabilities=planning_capabilities,
        )

    async def _wait_for_completion_streaming(
        self,
        client,
        *,
        thread_id: str,
        turn_id: str,
        deadline: float,
        context,
    ):
        completed_agent_messages: list[dict[str, object]] = []
        extractor = StructuredFinalAnswerDeltaExtractor()
        answer_item_id: str | None = None
        streaming_enabled = True
        for _ in range(_MAX_EVENTS):
            if self._cancelled():
                await _best_effort_interrupt(client, thread_id, turn_id)
                raise CodexAgentError("agent_cancelled")
            event = await client.next_event(timeout=_remaining(deadline))
            if "id" in event:
                raise CodexAgentError("codex_server_request_not_allowed")
            method = event.get("method")
            params = event.get("params")
            if not isinstance(method, str):
                raise CodexAgentError("codex_event_invalid")
            if method == "error":
                _validate_decision_error_event(
                    params,
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
                continue
            _validate_decision_notification(method, params, thread_id=thread_id, turn_id=turn_id)
            if method == "item/agentMessage/delta":
                item_id, delta = _agent_message_delta(
                    params,
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
                if answer_item_id is None:
                    answer_item_id = item_id
                elif item_id != answer_item_id:
                    raise CodexAgentError("codex_answer_delta_item_mismatch")
                if streaming_enabled and delta:
                    try:
                        chunks = extractor.feed(delta)
                    except AnswerStreamError:
                        # Provisional streaming is not authoritative. Disable it for this provider
                        # turn and let the normal final structured-output validation decide success.
                        streaming_enabled = False
                    else:
                        for chunk in chunks:
                            if not _emit_answer_delta(context, chunk):
                                streaming_enabled = False
                                break
                continue
            if method == "item/completed":
                item = _validate_completed_item(
                    params,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    dynamic_call_ids=set(),
                )
                if item.get("type") == "agentMessage":
                    completed_agent_messages.append(item)
                continue
            if method != "turn/completed":
                continue
            if not isinstance(params, dict) or params.get("threadId") != thread_id:
                raise CodexAgentError("codex_turn_completion_mismatch")
            turn = params.get("turn")
            if not isinstance(turn, dict) or turn.get("id") != turn_id:
                raise CodexAgentError("codex_turn_completion_mismatch")
            if turn.get("status") == "interrupted":
                raise CodexAgentError("agent_cancelled")
            if turn.get("status") != "completed" or turn.get("error") not in (None, {}):
                raise _decision_terminal_error(turn.get("error"), host_effect_safe=True)
            return _with_completed_agent_messages(turn, completed_agent_messages)
        raise CodexAgentError("codex_event_budget_exceeded")


def _agent_message_delta(params, *, thread_id: str, turn_id: str) -> tuple[str, str]:
    expected = {"delta", "itemId", "threadId", "turnId"}
    if not isinstance(params, dict) or set(params) != expected:
        raise CodexAgentError("codex_answer_delta_invalid")
    item_id = params.get("itemId")
    delta = params.get("delta")
    if (
        params.get("threadId") != thread_id
        or params.get("turnId") != turn_id
        or not isinstance(item_id, str)
        or not 1 <= len(item_id) <= _MAX_ITEM_ID
        or not isinstance(delta, str)
        or len(delta) > _MAX_PROVIDER_DELTA
        or "\x00" in delta
    ):
        raise CodexAgentError("codex_answer_delta_invalid")
    return item_id, delta


def _emit_answer_delta(context, text: str) -> bool:
    try:
        context.emit("answer.delta", "Respuesta", {"text": text})
    except Exception:  # noqa: BLE001 - live UX cannot become business authority
        return False
    return True


def install_codex_streaming() -> None:
    """Install the streaming subclass at the existing provider seam.

    ``embedded_runtime_host_loop`` imports ``CodexDecisionEngine`` from the module after package
    initialization, so replacing the symbol here changes only the provider adapter implementation;
    the host loop, capability authority, policy, approval and write lifecycle remain unchanged.
    """

    from . import codex_decision

    if codex_decision.CodexDecisionEngine is not StreamingCodexDecisionEngine:
        codex_decision.CodexDecisionEngine = StreamingCodexDecisionEngine
