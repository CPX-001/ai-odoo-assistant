"""Streaming specialization for the unified Codex agent."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import replace
from time import monotonic

from pydantic import ValidationError

from odoo_ai.adapters.agent_streaming import AnswerMarkdownDeltaExtractor
from odoo_ai.adapters.agent_timing import log_agent_timing
from odoo_ai.adapters.codex_engine import (
    CodexEngineError,
    _best_effort_interrupt,
    _codex_dynamic_tool_bindings,
    _decode_agent_candidate_arguments,
    _parse_structured_object,
    _remaining_seconds,
    _validate_thread_result,
    _validated_agent_output_schema,
    codex_dynamic_tools,
)
from odoo_ai.adapters.codex_runtime import CodexAppServerClient, CodexRuntimeError
from odoo_ai.adapters.codex_stream_wait import wait_for_completion_with_deltas
from odoo_ai.adapters.unified_agent_engine import (
    UnifiedAgentCodexAppServerEngine,
    _serialize_unified_context,
    _UNIFIED_AGENT_INSTRUCTIONS,
)
from odoo_ai.application.agent_events import AgentDeltaSink, current_agent_delta_sink
from odoo_ai.contracts import AgentCandidateOutput, ContextPack, ToolSpec

LOGGER = logging.getLogger(__name__)
_STREAM_CHUNK_CHARS = 2048


class StreamingUnifiedAgentCodexAppServerEngine(UnifiedAgentCodexAppServerEngine):
    """Use the normal engine unless the current request bound a provisional delta sink."""

    async def run_agent_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
    ) -> AgentCandidateOutput:
        sink = current_agent_delta_sink()
        if sink is None:
            return await super().run_agent_turn(context, tools)
        model = context.user.reasoning_model
        if model and model != self._settings.model:
            inner = StreamingUnifiedAgentCodexAppServerEngine(
                replace(self._settings, model=model),
                limits=self._limits,
                tool_executor_factory=self._tool_executor_factory,
            )
            try:
                return await inner._run_streaming_agent_turn(context, tools, sink)
            finally:
                self.last_metadata = inner.last_metadata
        return await self._run_streaming_agent_turn(context, tools, sink)

    async def _run_streaming_agent_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        sink: AgentDeltaSink,
    ) -> AgentCandidateOutput:
        started = monotonic()
        model: str | None = None
        provider: str | None = None
        try:
            if not self._settings.experimental_api:
                raise CodexEngineError("codex_experimental_api_required")
            if tools and self._tool_executor_factory is None:
                raise CodexEngineError("codex_tool_executor_unavailable")
            if context.workflow_hint is not None:
                raise CodexEngineError("codex_agent_context_invalid")
            schema = _validated_agent_output_schema(
                AgentCandidateOutput.model_json_schema(),
                self._limits,
            )
            turn_input = _serialize_unified_context(
                context,
                limits=self._limits,
                tool_names=[tool.name for tool in tools],
            )
            extractor = AnswerMarkdownDeltaExtractor(
                max_output_bytes=self._limits.max_answer_bytes
            )

            async def raw_delta_sink(raw_delta: str) -> None:
                visible = extractor.feed(raw_delta)
                for part in _chunk_visible_text(visible):
                    emitted = sink(part)
                    if inspect.isawaitable(emitted):
                        await emitted

            async with self._executor_context(context, tools) as executor:
                phase_started = monotonic()
                client = await CodexAppServerClient.start(self._settings)
                log_agent_timing("codex_app_server_startup_initialize", phase_started)
                async with client:
                    turn_deadline = monotonic() + self._settings.turn_timeout_seconds
                    phase_started = monotonic()
                    thread_result = await client.request(
                        "thread/start",
                        {
                            **client.thread_policy.start_params(),
                            "baseInstructions": _UNIFIED_AGENT_INSTRUCTIONS,
                            "dynamicTools": codex_dynamic_tools(tools),
                        },
                        timeout_seconds=_remaining_seconds(turn_deadline),
                    )
                    log_agent_timing("codex_thread_start", phase_started)
                    thread_id, model, provider = _validate_thread_result(thread_result)

                    phase_started = monotonic()
                    turn_id = await self._start_turn(
                        client,
                        thread_id=thread_id,
                        turn_input=turn_input,
                        output_schema=schema,
                        deadline=turn_deadline,
                    )
                    log_agent_timing("codex_turn_start", phase_started)

                    phase_started = monotonic()
                    try:
                        completed_turn, _ = await wait_for_completion_with_deltas(
                            client,
                            thread_id=thread_id,
                            turn_id=turn_id,
                            executor=executor,
                            dynamic_tool_names=_codex_dynamic_tool_bindings(tools),
                            deadline=turn_deadline,
                            max_events=self._limits.max_events,
                            raw_delta_sink=raw_delta_sink,
                        )
                    except BaseException:
                        await _best_effort_interrupt(
                            client,
                            thread_id=thread_id,
                            turn_id=turn_id,
                        )
                        raise
                    finally:
                        log_agent_timing("codex_reasoning_and_tools", phase_started)

                    try:
                        raw_candidate = _decode_agent_candidate_arguments(
                            _parse_structured_object(
                                completed_turn,
                                limits=self._limits,
                            ),
                            limits=self._limits,
                        )
                        candidate = AgentCandidateOutput.model_validate(raw_candidate)
                    except ValidationError:
                        raise CodexEngineError("codex_agent_output_invalid") from None
        except CodexEngineError as error:
            LOGGER.warning("Codex streaming agent turn failed: %s", error.code)
            self._set_metadata(
                started,
                status="error",
                error_code=error.code,
                model=model,
                provider=provider,
            )
            raise
        except CodexRuntimeError as error:
            wrapped = CodexEngineError(error.code)
            self._set_metadata(
                started,
                status="error",
                error_code=wrapped.code,
                model=model,
                provider=provider,
            )
            raise wrapped from None
        except (asyncio.CancelledError, KeyboardInterrupt):
            self._set_metadata(
                started,
                status="interrupted",
                error_code="codex_turn_interrupted",
                model=model,
                provider=provider,
            )
            raise
        except Exception:
            wrapped = CodexEngineError("codex_engine_failed")
            self._set_metadata(
                started,
                status="error",
                error_code=wrapped.code,
                model=model,
                provider=provider,
            )
            raise wrapped from None
        finally:
            log_agent_timing("codex_total", started)

        self._set_metadata(
            started,
            status="ok",
            error_code=None,
            model=model,
            provider=provider,
        )
        return candidate


def _chunk_visible_text(value: str):
    for start in range(0, len(value), _STREAM_CHUNK_CHARS):
        chunk = value[start : start + _STREAM_CHUNK_CHARS]
        if chunk:
            yield chunk
