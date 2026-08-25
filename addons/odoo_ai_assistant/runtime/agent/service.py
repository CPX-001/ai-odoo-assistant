"""Provider-neutral embedded agent orchestration.

The service knows the extension runtime, not Codex, Odoo HTTP, SQLAlchemy, or legacy
ToolRegistry. A ReasoningEngine receives the effective registry views and can invoke
only the supplied CapabilityExecutor for direct reasoning capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..capabilities import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityError,
    CapabilityExecutor,
    CapabilityRegistry,
    JsonValue,
)
from ..capabilities.validation import validate_payload


class AgentTurnError(RuntimeError):
    """Sanitized embedded-agent failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlannedCapability:
    capability: str
    arguments: dict[str, JsonValue]
    summary: str


@dataclass(frozen=True, slots=True)
class AgentReasoningResult:
    answer: str
    confidence: str
    plan: tuple[PlannedCapability, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    answer: str
    confidence: str
    plan: tuple[PlannedCapability, ...]


class ReasoningEngine(Protocol):
    async def run_agent_turn(
        self,
        *,
        message: str,
        conversation_summary: str,
        context: CapabilityContext,
        reasoning_capabilities: tuple[CapabilityDefinition, ...],
        planning_capabilities: tuple[CapabilityDefinition, ...],
        executor: CapabilityExecutor,
    ) -> AgentReasoningResult: ...


class AgentTurnService:
    """Run one turn from the authoritative CapabilityRegistry views."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        context: CapabilityContext,
        executor: CapabilityExecutor,
        reasoning_engine: ReasoningEngine,
    ) -> None:
        self._registry = registry
        self._context = context
        self._executor = executor
        self._reasoning_engine = reasoning_engine

    async def run(
        self,
        *,
        message: str,
        conversation_summary: str = "",
    ) -> AgentTurnResult:
        if getattr(self._context.env, "su", True):
            raise AgentTurnError("agent_superuser_forbidden")
        if (
            not isinstance(message, str)
            or not 1 <= len(message.strip()) <= 4_000
            or "\x00" in message
        ):
            raise AgentTurnError("agent_message_invalid")
        if (
            not isinstance(conversation_summary, str)
            or len(conversation_summary) > 8_000
            or "\x00" in conversation_summary
        ):
            raise AgentTurnError("agent_history_invalid")

        reasoning = self._registry.for_reasoning(self._context)
        planning = self._registry.for_planning(self._context)
        try:
            result = await self._reasoning_engine.run_agent_turn(
                message=message,
                conversation_summary=conversation_summary,
                context=self._context,
                reasoning_capabilities=reasoning,
                planning_capabilities=planning,
                executor=self._executor,
            )
        except (AgentTurnError, CapabilityError):
            raise
        except Exception as error:  # noqa: BLE001 - provider boundary is sanitized
            raise AgentTurnError("agent_reasoning_failed") from error
        if not isinstance(result, AgentReasoningResult):
            raise AgentTurnError("agent_reasoning_result_invalid")
        answer = result.answer.strip()
        if not 1 <= len(answer) <= 16_384 or "\x00" in answer:
            raise AgentTurnError("agent_answer_invalid")
        if result.confidence not in {"high", "medium", "low"}:
            raise AgentTurnError("agent_confidence_invalid")
        plan = self._validate_plan(result.plan, planning)
        return AgentTurnResult(
            answer=answer,
            confidence=result.confidence,
            plan=plan,
        )

    def _validate_plan(
        self,
        plan: tuple[PlannedCapability, ...],
        planning: tuple[CapabilityDefinition, ...],
    ) -> tuple[PlannedCapability, ...]:
        policy = self._context.metadata.get("capability_policy", {})
        maximum = policy.get("max_write_steps_per_plan", 12)
        if type(maximum) is not int or not 0 <= maximum <= 12:
            raise AgentTurnError("agent_policy_invalid")
        if not isinstance(plan, tuple) or len(plan) > maximum:
            raise AgentTurnError("agent_plan_limit_exceeded")
        allowed = {definition.name: definition for definition in planning}
        normalized: list[PlannedCapability] = []
        for step in plan:
            if not isinstance(step, PlannedCapability):
                raise AgentTurnError("agent_plan_invalid")
            definition = allowed.get(step.capability)
            if definition is None:
                raise AgentTurnError("agent_plan_capability_not_allowed")
            if (
                not isinstance(step.arguments, dict)
                or not isinstance(step.summary, str)
                or not 1 <= len(step.summary.strip()) <= 512
                or "\x00" in step.summary
            ):
                raise AgentTurnError("agent_plan_invalid")
            validate_payload(
                step.arguments,
                definition.input_schema,
                max_bytes=definition.max_input_bytes,
                error_code="agent_plan_arguments_invalid",
            )
            normalized.append(
                PlannedCapability(
                    capability=definition.name,
                    arguments=dict(step.arguments),
                    summary=" ".join(step.summary.split()),
                )
            )
        return tuple(normalized)
