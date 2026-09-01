"""Turn-scoped Codex App Server session reuse and adaptive effort mapping.

Odoo remains the durable host. This adapter only keeps one ephemeral App Server process alive for
the sequence of provider decisions made inside one AgentTurnService decision loop. Each decision
still starts a fresh ephemeral Codex thread and receives the complete host-authored bounded working
state, so provider-private thread history is not business durability.
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

_INSTALLED = False
_CODEX_AUTO_EFFORT = {"light": "low", "balanced": "medium", "deep": "high"}
_EFFICIENCY_INSTRUCTIONS = """

For large exact record selections, prefer odoo.query_record_ids when it is available and the
filter/schema are already grounded; it returns bounded identities without spending model context
on fields that are not needed. For irreversible deletion of more than 50 explicit targets, prefer
odoo.records.bulk_delete when available. The older 50-row chunking rule applies to the ordinary
odoo.records.batch_mutate capability, not to the dedicated bounded bulk-delete capability. Continue
query_record_ids from next_offset only when more than its own bulk page is required.
"""


class ReusableCodexDecisionEngine(StreamingCodexDecisionEngine):
    """Reuse process+initialize within one host decision loop; preserve fresh decision threads."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session_client = None
        self._session_decisions = 0

    async def _client_for_decision(self, timing):
        if self._session_client is not None:
            return self._session_client, True
        self._session_client = await _CodexClient.start(self._settings, timing=timing)
        return self._session_client, False

    async def aclose(self) -> None:
        client = self._session_client
        self._session_client = None
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
    try:
        context.emit(
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
    except Exception:  # noqa: BLE001 - diagnostics do not control the turn
        return


def _emit_session_diagnostic(context, *, reused: bool, decision_index: int) -> None:
    try:
        context.emit(
            "diagnostic.provider.session",
            "Provider session lifecycle",
            {
                "process_reused": reused,
                "decision_index": decision_index,
                "thread_reused": False,
            },
        )
    except Exception:  # noqa: BLE001 - diagnostics do not control the turn
        return


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
    if _EFFICIENCY_INSTRUCTIONS.strip() not in codex_decision._DECISION_INSTRUCTIONS:
        codex_decision._DECISION_INSTRUCTIONS += _EFFICIENCY_INSTRUCTIONS
    _INSTALLED = True


__all__ = ["ReusableCodexDecisionEngine", "install_codex_session_reuse"]
