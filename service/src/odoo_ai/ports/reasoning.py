"""Provider-neutral reasoning engine boundary."""

from typing import Protocol

from odoo_ai.contracts import AnswerEnvelope, ContextPack, ToolSpec


class ReasoningEngine(Protocol):
    """Run one isolated turn using explicit context, tools, and output schema."""

    async def run_turn(
        self,
        context: ContextPack,
        tools: list[ToolSpec],
        output_schema: dict[str, object],
    ) -> AnswerEnvelope: ...
