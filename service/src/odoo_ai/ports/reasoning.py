"""Provider-neutral reasoning engine boundary."""

from typing import Protocol

from odoo_ai.contracts import AgentCandidateOutput, AnswerEnvelope, ContextPack, ToolSpec


class ReasoningEngineError(RuntimeError):
    """Sanitized failure exposed by a reasoning-engine implementation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReasoningEngine(Protocol):
    """Run one isolated turn using explicit context, tools, and output schema."""

    async def run_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        output_schema: dict[str, object],
    ) -> AnswerEnvelope: ...


class AgentReasoningEngine(Protocol):
    """Propose a unified plan; the implementation receives no authorization capability."""

    async def run_agent_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
    ) -> AgentCandidateOutput: ...
