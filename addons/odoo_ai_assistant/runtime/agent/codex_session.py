"""Turn-scoped Codex App Server session reuse and adaptive effort mapping.

Odoo remains the durable host. This adapter keeps one ephemeral App Server process alive for the
sequence of provider decisions made inside one AgentTurnService decision loop. Provider-specific
transport lifecycle and reasoning-effort mapping stay here; business/tool-selection guidance stays
in provider-neutral capability and Skill metadata.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from . import codex, codex_decision
from .codex import (
    CodexAgentError,
    _CodexClient,
    _provider_timing_recorder,
    _remaining,
    _thread_id,
    _turn_id,
)
from .codex_decision import (
    _codex_next_decision_schema,
    _decision_instructions,
    _decision_result,
    _decision_turn_input,
    _is_simple_social_message,
)
from .codex_streaming import (
    StreamingCodexDecisionEngine,
    _long_answer_stream_requested,
    _streaming_thread_options,
)
from .decision_validation import validate_next_decision
from .reasoning_effort import AutoReasoningRoute, resolve_auto_reasoning_route
from .telemetry import emit_optional_telemetry

_INSTALLED = False
_CODEX_AUTO_EFFORT = {"light": "low", "balanced": "medium", "deep": "high"}


class _CompletedTurnEventFilter:
    """Ignore late notifications only after their provider turn is already terminal.

    App Server subscriptions can emit thread status/token/lifecycle notifications after
    ``turn/completed``. They belong to an already-settled provider turn and must not poison identity
    validation for the next fresh thread on the reused connection. Server requests are never
    discarded: an event carrying an ``id`` still crosses the normal fail-closed boundary.
    """

    def __init__(self, client, *, completed_threads: set[str], completed_turns: set[str]) -> None:
        self._client = client
        self._completed_threads = completed_threads
        self._completed_turns = completed_turns

    def __getattr__(self, name):
        return getattr(self._client, name)

    async def next_event(self, *, timeout: float):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            event = await self._client.next_event(timeout=_remaining(deadline))
            if _late_completed_notification(
                event,
                completed_threads=self._completed_threads,
                completed_turns=self._completed_turns,
            ):
                continue
            return event


class ReusableCodexDecisionEngine(StreamingCodexDecisionEngine):
    """Reuse process+initialize within one host decision loop; preserve fresh decision threads."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session_client = None
        self._session_decisions = 0
        self._completed_threads: set[str] = set()
        self._completed_turns: set[str] = set()

    async def _client_for_decision(self, timing):
        if self._session_client is not None:
            return self._session_client, True
        self._session_client = await _CodexClient.start(self._settings, timing=timing)
        return self._session_client, False

    async def aclose(self) -> None:
        client = self._session_client
        self._session_client = None
        self._completed_threads.clear()
        self._completed_turns.clear()
        if client is not None:
            await client.close()

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
        effective_settings, route = _settings_for_decision(
            self._settings,
            message=message,
            screen=context.screen,
            working_items=working_items,
        )
        if route is not None:
            _emit_reasoning_route(context, route, effective_settings.reasoning_effort)

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
        client, reused = await self._client_for_decision(timing)
        self._session_decisions += 1
        _emit_session_diagnostic(
            context,
            reused=reused,
            decision_index=self._session_decisions,
        )
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
                **_streaming_thread_options(effective_settings),
                "baseInstructions": _decision_instructions(final_answer_only),
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
        filtered_client = _CompletedTurnEventFilter(
            client,
            completed_threads=self._completed_threads,
            completed_turns=self._completed_turns,
        )
        completed = await self._wait_for_completion_streaming(
            filtered_client,
            thread_id=thread_id,
            turn_id=turn_id,
            deadline=deadline,
            context=context,
            timing=timing,
        )
        self._completed_threads.add(thread_id)
        self._completed_turns.add(turn_id)
        return validate_next_decision(
            _decision_result(completed),
            reasoning_capabilities=reasoning_capabilities,
            planning_capabilities=planning_capabilities,
        )


def _late_completed_notification(event, *, completed_threads, completed_turns) -> bool:
    if not isinstance(event, dict) or "id" in event or not isinstance(event.get("method"), str):
        return False
    params = event.get("params")
    if not isinstance(params, dict):
        return False
    thread_id = params.get("threadId")
    turn_id = params.get("turnId")
    return (
        isinstance(thread_id, str)
        and thread_id in completed_threads
        or isinstance(turn_id, str)
        and turn_id in completed_turns
    )


def _settings_for_decision(settings, *, message, screen, working_items):
    if settings.reasoning_effort != "auto":
        return settings, None
    route = resolve_auto_reasoning_route(
        message=message,
        screen=screen,
        working_items=working_items,
    )
    return replace(settings, reasoning_effort=_CODEX_AUTO_EFFORT[route.tier]), route


def _emit_reasoning_route(context, route: AutoReasoningRoute, effort: str | None) -> None:
    emit_optional_telemetry(
        context,
        "diagnostic.reasoning_route",
        "Adaptive reasoning route",
        {
            "mode": "auto",
            "tier": route.tier,
            "provider_effort": effort,
            "complexity_score": route.complexity_score,
            "reasons": list(route.reasons),
        },
    )


def _emit_session_diagnostic(context, *, reused: bool, decision_index: int) -> None:
    emit_optional_telemetry(
        context,
        "diagnostic.provider.session",
        "Provider session lifecycle",
        {
            "process_reused": reused,
            "decision_index": decision_index,
            "thread_reused": False,
        },
    )


def _legacy_model_thread_options(settings):
    """Keep the rollback-only monolithic Codex path valid for an Auto snapshot."""

    if settings.reasoning_effort == "auto":
        settings = replace(settings, reasoning_effort="low")
    return _ORIGINAL_MODEL_THREAD_OPTIONS(settings)


_ORIGINAL_MODEL_THREAD_OPTIONS = codex._model_thread_options


def install_codex_session_reuse() -> None:
    """Install at the existing provider seam; host orchestration remains provider-neutral."""

    global _INSTALLED
    if _INSTALLED:
        return
    codex_decision.CodexDecisionEngine = ReusableCodexDecisionEngine
    codex._model_thread_options = _legacy_model_thread_options
    _INSTALLED = True


__all__ = ["ReusableCodexDecisionEngine", "install_codex_session_reuse"]
