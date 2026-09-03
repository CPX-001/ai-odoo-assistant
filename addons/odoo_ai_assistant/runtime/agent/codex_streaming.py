"""Codex answer and readable-reasoning-summary streaming without changing host authority.

The provider still returns one validated ``NextDecision``. Provisional final-answer text and
provider-declared readable reasoning summaries are optional presentation channels. Raw reasoning
(``item/reasoning/textDelta``) is deliberately ignored and can never cross the public live seam.
"""

from __future__ import annotations

import asyncio

from .answer_stream import AnswerStreamError, StructuredFinalAnswerDeltaExtractor
from .codex import _provider_timing_recorder
from .codex_decision import (
    _MAX_EVENTS,
    CodexAgentError,
    _best_effort_interrupt,
    _codex_next_decision_schema,
    _CodexClient,
    _decision_instructions,
    _decision_result,
    _decision_terminal_error,
    _decision_turn_input,
    _is_simple_social_message,
    _model_thread_options,
    _remaining,
    _thread_id,
    _turn_id,
    _validate_completed_item,
    _validate_decision_error_event,
    _validate_decision_notification,
    _with_completed_agent_messages,
)
from .codex_decision import (
    CodexDecisionEngine as _BaseCodexDecisionEngine,
)
from .decision_validation import validate_next_decision
from .telemetry import emit_optional_telemetry

_MAX_PROVIDER_DELTA = 16 * 1024
_MAX_PUBLIC_REASONING_DELTA = 2 * 1024
_MAX_ITEM_ID = 256
_MAX_SUMMARY_INDEX = 64


def _streaming_thread_options(settings):
    """Request only the provider's supported readable summary channel.

    ``auto`` lets the current App Server/model negotiate whether a readable summary is available.
    It is intentionally unrelated to raw reasoning, which remains ignored below.
    """

    options = dict(_model_thread_options(settings))
    config = dict(options.get("config") or {})
    config.setdefault("model_reasoning_summary", "auto")
    options["config"] = config
    return options


class StreamingCodexDecisionEngine(_BaseCodexDecisionEngine):
    """Current Codex decision adapter with safe provisional presentation streams."""

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
        timing = _provider_timing_recorder(context)
        timing("runtime_started")
        final_answer_only = _is_simple_social_message(message)
        wire_schema = _codex_next_decision_schema(
            final_answer_only=final_answer_only,
            working_items=working_items,
        )
        prompt_schema_streaming = _long_answer_stream_requested(message)
        turn_input = _decision_turn_input(
            message=message,
            conversation_summary=conversation_summary,
            context=context,
            reasoning=reasoning_capabilities,
            planning=planning_capabilities,
            working_items=working_items,
            remaining_budgets=remaining_budgets or {},
            wire_schema=wire_schema if prompt_schema_streaming else None,
        )
        client = await _CodexClient.start(self._settings, timing=timing)
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
                    **_streaming_thread_options(self._settings),
                    "baseInstructions": _decision_instructions(
                        final_answer_only,
                        response_detail=self._settings.response_detail,
                    ),
                },
                timeout=_remaining(deadline),
            )
            thread_id = _thread_id(thread_result)
            timing("provider_thread_started")
            turn_params = {
                "input": [{"type": "text", "text": turn_input}],
                "threadId": thread_id,
            }
            if not prompt_schema_streaming:
                turn_params["outputSchema"] = wire_schema
            turn_result = await client.request(
                "turn/start",
                turn_params,
                timeout=_remaining(deadline),
            )
            turn_id = _turn_id(turn_result)
            timing("provider_turn_started")
            completed = await self._wait_for_completion_streaming(
                client,
                thread_id=thread_id,
                turn_id=turn_id,
                deadline=deadline,
                context=context,
                timing=timing,
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
        timing,
    ):
        completed_agent_messages: list[dict[str, object]] = []
        extractor = StructuredFinalAnswerDeltaExtractor()
        answer_item_id: str | None = None
        streaming_enabled = True
        reasoning_summary_enabled = True
        provider_delta_observed = False
        answer_chunk_observed = False
        for _ in range(_MAX_EVENTS):
            if self._cancelled():
                await _best_effort_interrupt(client, thread_id, turn_id)
                raise CodexAgentError("agent_cancelled")
            event = await client.next_event(timeout=_remaining(deadline))
            timing("first_provider_event")
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
            if method == "item/reasoning/summaryTextDelta":
                item_id, summary_index, delta = _reasoning_summary_delta(
                    params,
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
                if reasoning_summary_enabled and delta:
                    reasoning_summary_enabled = _emit_reasoning_summary_delta(
                        context,
                        item_id=item_id,
                        summary_index=summary_index,
                        text=delta,
                    )
                continue
            if method == "item/reasoning/textDelta":
                # This is raw/private reasoning. It is intentionally inert and never projected.
                continue
            if method == "item/agentMessage/delta":
                timing("first_answer_delta")
                item_id, delta = _agent_message_delta(
                    params,
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
                if answer_item_id is None:
                    answer_item_id = item_id
                elif item_id != answer_item_id:
                    # App Server may start a second agent-message item in the same turn (for
                    # example while an interactive redirect is arriving). The completed turn's
                    # last validated agent message remains authoritative. Provisional streaming
                    # is presentation-only, so stop projecting deltas instead of failing an
                    # otherwise valid provider decision.
                    answer_item_id = item_id
                    streaming_enabled = False
                if delta and not provider_delta_observed:
                    provider_delta_observed = True
                    _emit_streaming_diagnostic(
                        context,
                        "diagnostic.streaming.provider_delta",
                        chars=len(delta),
                    )
                if streaming_enabled and delta:
                    try:
                        chunks = extractor.feed(delta)
                    except AnswerStreamError:
                        # Provisional streaming is not authoritative. Disable it for this provider
                        # turn and let the normal final structured-output validation decide success.
                        streaming_enabled = False
                    else:
                        for chunk in chunks:
                            if not answer_chunk_observed:
                                answer_chunk_observed = True
                                _emit_streaming_diagnostic(
                                    context,
                                    "diagnostic.streaming.answer_chunk",
                                    chars=len(chunk),
                                )
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
            timing("provider_turn_completed")
            return _with_completed_agent_messages(turn, completed_agent_messages)
        raise CodexAgentError("codex_event_budget_exceeded")


def _long_answer_stream_requested(message: object) -> bool:
    """Use the prompt-carried host schema for every real product turn.

    The legacy helper name is retained because tests and downstream code import it. App Server can
    buffer a provider-side structured-output string until the JSON object closes, which makes a
    normal short turn look completely non-streaming. Keeping the exact wire schema inside the
    host-authored prompt lets ordinary ``item/agentMessage/delta`` notifications arrive while the
    completed message still crosses the same strict JSON parser and ``NextDecision`` validator.

    This is presentation/transport only: the model gains no execution authority, and malformed
    completed output still fails closed.
    """

    return isinstance(message, str) and bool(message.strip())


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


def _reasoning_summary_delta(
    params,
    *,
    thread_id: str,
    turn_id: str,
) -> tuple[str, int, str]:
    expected = {"delta", "itemId", "summaryIndex", "threadId", "turnId"}
    if not isinstance(params, dict) or set(params) != expected:
        raise CodexAgentError("codex_reasoning_summary_delta_invalid")
    item_id = params.get("itemId")
    summary_index = params.get("summaryIndex")
    delta = params.get("delta")
    if (
        params.get("threadId") != thread_id
        or params.get("turnId") != turn_id
        or not isinstance(item_id, str)
        or not 1 <= len(item_id) <= _MAX_ITEM_ID
        or type(summary_index) is not int
        or not 0 <= summary_index <= _MAX_SUMMARY_INDEX
        or not isinstance(delta, str)
        or len(delta) > _MAX_PROVIDER_DELTA
        or "\x00" in delta
    ):
        raise CodexAgentError("codex_reasoning_summary_delta_invalid")
    return item_id, summary_index, delta


def _emit_answer_delta(context, text: str) -> bool:
    return emit_optional_telemetry(
        context,
        "answer.delta",
        "Respuesta",
        {"text": text},
    )


def _emit_streaming_diagnostic(context, event_type: str, *, chars: int) -> None:
    """Record only timing-stage metadata; never persist provisional answer text here."""

    emit_optional_telemetry(
        context,
        event_type,
        "Streaming timing",
        {"chars": chars},
    )


def _emit_reasoning_summary_delta(
    context,
    *,
    item_id: str,
    summary_index: int,
    text: str,
) -> bool:
    for start in range(0, len(text), _MAX_PUBLIC_REASONING_DELTA):
        chunk = text[start : start + _MAX_PUBLIC_REASONING_DELTA]
        if chunk and not emit_optional_telemetry(
            context,
            "reasoning.summary.delta",
            "Resumen de razonamiento",
            {
                "item_id": item_id,
                "summary_index": summary_index,
                "text": chunk,
            },
        ):
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
