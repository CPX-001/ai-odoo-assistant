"""Provider-neutral embedded agent orchestration.

The service owns the bounded host loop. Providers return one NextDecision at a time;
the host validates every decision against the effective CapabilityRegistry views and
executes only REASONING capabilities directly. PLAN proposals remain stage-only.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from ..capabilities import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityError,
    CapabilityExecutor,
    CapabilityRegistry,
    ExecutionAuthority,
    JsonValue,
)
from ..capabilities.validation import validate_payload
from .contracts import (
    FinalAnswer,
    NextDecision,
    PlanStepProposal,
    ReasoningCapabilityCall,
    decision_payload,
)
from .decision_validation import NextDecisionValidationError, validate_next_decision
from .working_transcript import (
    MAX_RESULT_BYTES,
    MAX_TRANSCRIPT_BYTES,
    WorkingItem,
    WorkingTranscriptError,
    append_working_item,
    call_state,
    transcript_payload,
    working_transcript_bytes,
)


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
    """Legacy monolithic provider contract kept only as rollback compatibility."""

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


class NextDecisionEngine(Protocol):
    async def next_decision(
        self,
        *,
        message: str,
        conversation_summary: str,
        context: CapabilityContext,
        reasoning_capabilities: tuple[CapabilityDefinition, ...],
        planning_capabilities: tuple[CapabilityDefinition, ...],
        working_items: tuple[dict[str, object], ...],
        remaining_budgets: dict[str, int],
    ) -> NextDecision: ...


PersistWorkingItems = Callable[
    [tuple[WorkingItem, ...]],
    None | Awaitable[None],
]

_DEFAULT_MAX_PROVIDER_DECISIONS = 12
_DEFAULT_MAX_CAPABILITY_CALLS = 8
_DEFAULT_MAX_CONSECUTIVE_CORRECTABLE_FAILURES = 3
_MAX_PROVIDER_DECISIONS = 32
_MAX_CAPABILITY_CALLS = 32
_MAX_CONSECUTIVE_CORRECTABLE_FAILURES = 8

# These failures are safe to expose privately to the next provider decision and may be repaired.
_CORRECTABLE_ERRORS = frozenset(
    {
        "agent_capability_arguments_invalid",
        "agent_plan_arguments_invalid",
        "agent_reasoning_capability_not_allowed",
        "agent_plan_capability_not_allowed",
        "capability_input_invalid",
        "capability_input_invalid_too_large",
        "capability_not_available",
        "capability_not_registered",
        "capability_call_limit_exceeded",
        "agent_capability_call_interrupted",
    }
)

# Authority/ACL failures may be explained by one final provider answer but must not trigger
# another capability execution in the same turn.
_TERMINAL_CALL_ERRORS = frozenset(
    {
        "access_denied",
        "capability_authority_mismatch",
        "capability_policy_denied",
        "capability_plan_approval_required",
    }
)


class AgentTurnService:
    """Run one turn from authoritative CapabilityRegistry views.

    New product composition passes ``decision_engine`` plus durable working items. The
    legacy ``reasoning_engine`` path is retained only as a bounded rollback seam until
    the convergence is fully validated in the real environment.
    """

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        context: CapabilityContext,
        executor: CapabilityExecutor,
        reasoning_engine: ReasoningEngine | None = None,
        decision_engine: NextDecisionEngine | None = None,
        working_items: tuple[WorkingItem, ...] = (),
        persist_working_items: PersistWorkingItems | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
        allow_plan_proposals: bool = False,
    ) -> None:
        if (reasoning_engine is None) == (decision_engine is None):
            raise AgentTurnError("agent_reasoning_engine_invalid")
        self._registry = registry
        self._context = context
        self._executor = executor
        self._reasoning_engine = reasoning_engine
        self._decision_engine = decision_engine
        self._working_items = tuple(working_items)
        self._persist_working_items = persist_working_items
        self._cancelled = cancellation_requested or (lambda: False)
        self._allow_plan_proposals = bool(allow_plan_proposals)

    @property
    def working_items(self) -> tuple[WorkingItem, ...]:
        return self._working_items

    async def run(
        self,
        *,
        message: str,
        conversation_summary: str = "",
    ) -> AgentTurnResult:
        self._validate_request(message, conversation_summary)
        reasoning = self._registry.for_reasoning(self._context)
        planning = self._registry.for_planning(self._context)
        if self._decision_engine is not None:
            return await self._run_decision_loop(
                message=message,
                conversation_summary=conversation_summary,
                reasoning=reasoning,
                planning=planning,
            )
        return await self._run_legacy(
            message=message,
            conversation_summary=conversation_summary,
            reasoning=reasoning,
            planning=planning,
        )

    def _validate_request(self, message: str, conversation_summary: str) -> None:
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

    async def _run_legacy(
        self,
        *,
        message: str,
        conversation_summary: str,
        reasoning: tuple[CapabilityDefinition, ...],
        planning: tuple[CapabilityDefinition, ...],
    ) -> AgentTurnResult:
        engine = self._reasoning_engine
        if engine is None:
            raise AgentTurnError("agent_reasoning_engine_invalid")
        try:
            result = await engine.run_agent_turn(
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
        answer = _validated_answer(result.answer, result.confidence)
        plan = self._validate_plan(result.plan, planning)
        return AgentTurnResult(answer=answer, confidence=result.confidence, plan=plan)

    async def _run_decision_loop(
        self,
        *,
        message: str,
        conversation_summary: str,
        reasoning: tuple[CapabilityDefinition, ...],
        planning: tuple[CapabilityDefinition, ...],
    ) -> AgentTurnResult:
        engine = self._decision_engine
        if engine is None:
            raise AgentTurnError("agent_reasoning_engine_invalid")
        budgets = _loop_budgets(self._context)
        await self._ensure_user_input(message)
        resumed = self._resume_terminal()
        if resumed is not None:
            return resumed
        await self._close_interrupted_calls()

        provider_decisions = _provider_decisions_used(self._working_items)
        capability_calls = _capability_calls_used(self._working_items)
        consecutive_failures = _trailing_failure_count(self._working_items)
        terminal_error = _terminal_error_pending(self._working_items)

        while provider_decisions < budgets["max_provider_decisions"]:
            self._ensure_not_cancelled()
            remaining = {
                "provider_decisions": budgets["max_provider_decisions"] - provider_decisions,
                "capability_calls": budgets["max_capability_calls"] - capability_calls,
                "correctable_failures": (
                    budgets["max_consecutive_correctable_failures"] - consecutive_failures
                ),
                "transcript_bytes": max(
                    0,
                    MAX_TRANSCRIPT_BYTES - working_transcript_bytes(self._working_items),
                ),
                "result_bytes": MAX_RESULT_BYTES,
            }
            decision_counted = False
            try:
                decision = await engine.next_decision(
                    message=message,
                    conversation_summary=conversation_summary,
                    context=self._context,
                    reasoning_capabilities=reasoning,
                    planning_capabilities=planning,
                    working_items=tuple(
                        item.payload() for item in self._working_items
                    ),
                    remaining_budgets=remaining,
                )
                provider_decisions += 1
                decision_counted = True
                decision = validate_next_decision(
                    decision,
                    reasoning_capabilities=reasoning,
                    planning_capabilities=planning,
                )
            except NextDecisionValidationError as error:
                if not decision_counted:
                    provider_decisions += 1
                rejected = getattr(error, "decision", None)
                if not isinstance(rejected, (ReasoningCapabilityCall, PlanStepProposal)):
                    raise AgentTurnError(error.code) from error
                if isinstance(rejected, ReasoningCapabilityCall):
                    capability_calls += 1
                    if capability_calls > budgets["max_capability_calls"]:
                        raise AgentTurnError("agent_capability_call_budget_exceeded") from error
                await self._record_rejected_decision(rejected, error.code)
                consecutive_failures += 1
                if consecutive_failures > budgets["max_consecutive_correctable_failures"]:
                    raise AgentTurnError("agent_correctable_failure_budget_exceeded") from error
                continue
            except (AgentTurnError, CapabilityError):
                raise
            except Exception as error:  # noqa: BLE001 - provider boundary stays sanitized
                code = getattr(error, "code", None)
                if isinstance(code, str):
                    raise AgentTurnError(code) from error
                raise AgentTurnError("agent_reasoning_failed") from error

            if terminal_error and not isinstance(decision, FinalAnswer):
                raise AgentTurnError("agent_terminal_capability_error_requires_final")

            if isinstance(decision, FinalAnswer):
                answer = _validated_answer(decision.answer, decision.confidence)
                self._working_items = append_working_item(
                    self._working_items,
                    "final_answer",
                    {"answer": answer, "confidence": decision.confidence},
                )
                await self._persist()
                return AgentTurnResult(answer=answer, confidence=decision.confidence, plan=())

            if isinstance(decision, PlanStepProposal):
                await self._record_decision(decision)
                if not self._allow_plan_proposals:
                    self._working_items = append_working_item(
                        self._working_items,
                        "capability_error",
                        {
                            "call_id": decision.call_id,
                            "capability": decision.capability,
                            "code": "agent_plan_proposal_not_enabled",
                        },
                    )
                    await self._persist()
                    raise AgentTurnError("agent_plan_proposal_not_enabled")
                self._working_items = append_working_item(
                    self._working_items,
                    "plan_step_proposed",
                    {
                        "call_id": decision.call_id,
                        "capability": decision.capability,
                        "arguments": dict(decision.arguments),
                        "user_summary": decision.user_summary,
                    },
                )
                await self._persist()
                return AgentTurnResult(
                    answer="He preparado la acción solicitada para revisión.",
                    confidence="high",
                    plan=(
                        PlannedCapability(
                            capability=decision.capability,
                            arguments=dict(decision.arguments),
                            summary=decision.user_summary,
                        ),
                    ),
                )

            if not isinstance(decision, ReasoningCapabilityCall):
                raise AgentTurnError("agent_next_decision_invalid")

            capability_calls += 1
            if capability_calls > budgets["max_capability_calls"]:
                raise AgentTurnError("agent_capability_call_budget_exceeded")

            if _definition_call_count(self._working_items, decision.capability) >= _definition_max_calls(
                reasoning,
                decision.capability,
            ):
                await self._record_decision(decision)
                self._working_items = append_working_item(
                    self._working_items,
                    "capability_error",
                    {
                        "call_id": decision.call_id,
                        "capability": decision.capability,
                        "code": "capability_call_limit_exceeded",
                    },
                )
                await self._persist()
                consecutive_failures += 1
                if consecutive_failures > budgets["max_consecutive_correctable_failures"]:
                    raise AgentTurnError("agent_correctable_failure_budget_exceeded")
                continue

            state = call_state(self._working_items, decision.call_id)
            if state is not None:
                raise AgentTurnError("agent_working_call_id_duplicate")

            await self._record_decision(decision)
            self._working_items = append_working_item(
                self._working_items,
                "capability_call",
                {
                    "call_id": decision.call_id,
                    "capability": decision.capability,
                    "arguments": dict(decision.arguments),
                },
            )
            await self._persist()
            self._ensure_not_cancelled()

            try:
                result = await self._execute_reasoning(decision)
            except CapabilityError as error:
                self._working_items = append_working_item(
                    self._working_items,
                    "capability_error",
                    {
                        "call_id": decision.call_id,
                        "capability": decision.capability,
                        "code": error.code,
                    },
                )
                await self._persist()
                if error.code in _TERMINAL_CALL_ERRORS:
                    terminal_error = True
                    consecutive_failures = 0
                    continue
                consecutive_failures += 1
                if (
                    error.code not in _CORRECTABLE_ERRORS
                    or consecutive_failures > budgets["max_consecutive_correctable_failures"]
                ):
                    raise AgentTurnError(error.code) from error
                continue

            try:
                self._working_items = append_working_item(
                    self._working_items,
                    "capability_result",
                    {
                        "call_id": decision.call_id,
                        "capability": decision.capability,
                        "result": dict(result.data),
                    },
                )
            except WorkingTranscriptError as error:
                if error.code != "agent_working_item_too_large":
                    raise AgentTurnError(error.code) from error
                self._working_items = append_working_item(
                    self._working_items,
                    "capability_error",
                    {
                        "call_id": decision.call_id,
                        "capability": decision.capability,
                        "code": "agent_capability_result_too_large",
                    },
                )
                await self._persist()
                consecutive_failures += 1
                if consecutive_failures > budgets["max_consecutive_correctable_failures"]:
                    raise AgentTurnError("agent_correctable_failure_budget_exceeded")
                continue
            await self._persist()
            consecutive_failures = 0
            terminal_error = False

        raise AgentTurnError("agent_provider_decision_budget_exceeded")

    async def _record_rejected_decision(
        self,
        decision: ReasoningCapabilityCall | PlanStepProposal,
        code: str,
    ) -> None:
        if call_state(self._working_items, decision.call_id) is not None:
            raise AgentTurnError("agent_working_call_id_duplicate")
        await self._record_decision(decision)
        self._working_items = append_working_item(
            self._working_items,
            "capability_error",
            {
                "call_id": decision.call_id,
                "capability": decision.capability,
                "code": code,
            },
        )
        await self._persist()

    async def _record_decision(
        self,
        decision: ReasoningCapabilityCall | PlanStepProposal,
    ) -> None:
        payload = decision_payload(decision)
        payload["decision_kind"] = payload.pop("kind")
        self._working_items = append_working_item(
            self._working_items,
            "assistant_decision",
            payload,
        )
        await self._persist()

    async def _execute_reasoning(self, decision: ReasoningCapabilityCall):
        cursor = getattr(self._context.env, "cr", None)
        savepoint = getattr(cursor, "savepoint", None)
        if callable(savepoint):
            with savepoint():
                return await self._executor.execute(
                    decision.capability,
                    decision.arguments,
                    authority=ExecutionAuthority.REASONING,
                )
        return await self._executor.execute(
            decision.capability,
            decision.arguments,
            authority=ExecutionAuthority.REASONING,
        )

    async def _ensure_user_input(self, message: str) -> None:
        if self._working_items:
            first = self._working_items[0]
            if first.kind != "user_input" or first.data.get("message") != message:
                raise AgentTurnError("agent_working_transcript_request_mismatch")
            return
        self._working_items = append_working_item(
            (),
            "user_input",
            {"message": message},
        )
        await self._persist()

    def _resume_terminal(self) -> AgentTurnResult | None:
        if not self._working_items:
            return None
        last = self._working_items[-1]
        if last.kind == "final_answer":
            answer = last.data.get("answer")
            confidence = last.data.get("confidence")
            if not isinstance(answer, str) or not isinstance(confidence, str):
                raise AgentTurnError("agent_working_transcript_invalid")
            return AgentTurnResult(
                answer=_validated_answer(answer, confidence),
                confidence=confidence,
                plan=(),
            )
        if last.kind == "plan_step_proposed":
            if not self._allow_plan_proposals:
                raise AgentTurnError("agent_plan_proposal_not_enabled")
            capability = last.data.get("capability")
            arguments = last.data.get("arguments")
            summary = last.data.get("user_summary")
            if (
                not isinstance(capability, str)
                or not isinstance(arguments, dict)
                or not isinstance(summary, str)
            ):
                raise AgentTurnError("agent_working_transcript_invalid")
            return AgentTurnResult(
                answer="He preparado la acción solicitada para revisión.",
                confidence="high",
                plan=(
                    PlannedCapability(
                        capability=capability,
                        arguments=dict(arguments),
                        summary=summary,
                    ),
                ),
            )
        return None

    async def _close_interrupted_calls(self) -> None:
        pending = _pending_decisions(self._working_items)
        for call_id, data in pending:
            decision_kind = data.get("decision_kind")
            capability = data.get("capability")
            code = (
                "agent_plan_proposal_interrupted"
                if decision_kind == "plan_step_proposal"
                else "agent_capability_call_interrupted"
            )
            self._working_items = append_working_item(
                self._working_items,
                "capability_error",
                {
                    "call_id": call_id,
                    "capability": capability if isinstance(capability, str) else "unknown",
                    "code": code,
                },
            )
        if pending:
            await self._persist()

    async def _persist(self) -> None:
        # Validate and bound before crossing the persistence boundary.
        transcript_payload(self._working_items)
        if self._persist_working_items is None:
            return
        try:
            pending = self._persist_working_items(self._working_items)
            if inspect.isawaitable(pending):
                await pending
        except AgentTurnError:
            raise
        except Exception as error:  # noqa: BLE001 - persistence boundary stays sanitized
            code = getattr(error, "code", None)
            if code == "agent_turn_lease_lost" or str(error) == "agent_turn_lease_lost":
                raise AgentTurnError("agent_turn_lease_lost") from error
            raise AgentTurnError("agent_working_transcript_persist_failed") from error

    def _ensure_not_cancelled(self) -> None:
        if self._cancelled():
            raise AgentTurnError("agent_cancelled")

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


def _validated_answer(answer: object, confidence: object) -> str:
    if (
        not isinstance(answer, str)
        or not 1 <= len(answer.strip()) <= 16_384
        or "\x00" in answer
    ):
        raise AgentTurnError("agent_answer_invalid")
    if confidence not in {"high", "medium", "low"}:
        raise AgentTurnError("agent_confidence_invalid")
    return answer.strip()


def _loop_budgets(context: CapabilityContext) -> dict[str, int]:
    policy = context.metadata.get("capability_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    values = {
        "max_provider_decisions": policy.get(
            "max_provider_decisions", _DEFAULT_MAX_PROVIDER_DECISIONS
        ),
        "max_capability_calls": policy.get(
            "max_capability_calls", _DEFAULT_MAX_CAPABILITY_CALLS
        ),
        "max_consecutive_correctable_failures": policy.get(
            "max_consecutive_correctable_failures",
            _DEFAULT_MAX_CONSECUTIVE_CORRECTABLE_FAILURES,
        ),
    }
    limits = {
        "max_provider_decisions": _MAX_PROVIDER_DECISIONS,
        "max_capability_calls": _MAX_CAPABILITY_CALLS,
        "max_consecutive_correctable_failures": _MAX_CONSECUTIVE_CORRECTABLE_FAILURES,
    }
    for key, value in values.items():
        if type(value) is not int or not 1 <= value <= limits[key]:
            raise AgentTurnError("agent_policy_invalid")
    return values


def _provider_decisions_used(items: tuple[WorkingItem, ...]) -> int:
    return sum(
        item.kind in {"assistant_decision", "final_answer"}
        for item in items
    )


def _capability_calls_used(items: tuple[WorkingItem, ...]) -> int:
    return sum(
        item.kind == "assistant_decision"
        and item.data.get("decision_kind") == "reasoning_capability_call"
        for item in items
    )


def _trailing_failure_count(items: tuple[WorkingItem, ...]) -> int:
    count = 0
    for item in reversed(items):
        if item.kind == "capability_error":
            count += 1
            continue
        if item.kind == "capability_result":
            return 0
        if item.kind in {"assistant_decision", "capability_call"}:
            continue
        break
    return count


def _terminal_error_pending(items: tuple[WorkingItem, ...]) -> bool:
    for item in reversed(items):
        if item.kind == "capability_result":
            return False
        if item.kind == "capability_error":
            return item.data.get("code") in _TERMINAL_CALL_ERRORS
    return False


def _definition_call_count(items: tuple[WorkingItem, ...], capability: str) -> int:
    return sum(
        item.kind == "assistant_decision"
        and item.data.get("decision_kind") == "reasoning_capability_call"
        and item.data.get("capability") == capability
        for item in items
    )


def _definition_max_calls(
    definitions: tuple[CapabilityDefinition, ...],
    capability: str,
) -> int:
    for definition in definitions:
        if definition.name == capability:
            return definition.max_calls
    raise AgentTurnError("agent_reasoning_capability_not_allowed")


def _pending_decisions(
    items: tuple[WorkingItem, ...],
) -> tuple[tuple[str, dict[str, object]], ...]:
    pending: list[tuple[str, dict[str, object]]] = []
    for item in items:
        if item.kind != "assistant_decision":
            continue
        call_id = item.data.get("call_id")
        if not isinstance(call_id, str):
            continue
        if call_state(items, call_id) == "pending":
            pending.append((call_id, dict(item.data)))
    return tuple(pending)
