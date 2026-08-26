"""Provider-neutral reasoning engine boundary for residual retrieval workflows."""

from typing import Protocol

from odoo_ai.contracts import AnswerEnvelope, ContextPack, ToolSpec


class ReasoningEngineError(RuntimeError):
    """Sanitized failure exposed by a reasoning-engine implementation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ReasoningEngine(Protocol):
    """Run one isolated read-only turn using explicit context and tools."""

    async def run_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        output_schema: dict[str, object],
    ) -> AnswerEnvelope: ...
