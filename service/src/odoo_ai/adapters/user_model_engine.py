"""Per-turn Codex model selection without mutating global runtime configuration."""

from __future__ import annotations

from dataclasses import replace

from odoo_ai.adapters.codex_engine import CodexAppServerEngine as BaseCodexAppServerEngine
from odoo_ai.contracts import AgentCandidateOutput, AnswerEnvelope, ContextPack, ToolSpec


class UserSelectableCodexAppServerEngine(BaseCodexAppServerEngine):
    """Use the authenticated user's model preference for only the current turn."""

    async def run_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        output_schema: dict[str, object],
    ) -> AnswerEnvelope:
        model = context.user.reasoning_model
        if not model or model == self._settings.model:
            return await super().run_turn(context, tools, output_schema)

        inner = BaseCodexAppServerEngine(
            replace(self._settings, model=model),
            limits=self._limits,
            tool_executor_factory=self._tool_executor_factory,
        )
        try:
            return await inner.run_turn(context, tools, output_schema)
        finally:
            self.last_metadata = inner.last_metadata

    async def run_agent_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
    ) -> AgentCandidateOutput:
        model = context.user.reasoning_model
        if not model or model == self._settings.model:
            return await super().run_agent_turn(context, tools)

        inner = BaseCodexAppServerEngine(
            replace(self._settings, model=model),
            limits=self._limits,
            tool_executor_factory=self._tool_executor_factory,
        )
        try:
            return await inner.run_agent_turn(context, tools)
        finally:
            self.last_metadata = inner.last_metadata
