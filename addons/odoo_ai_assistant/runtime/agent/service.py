"""Provider-neutral embedded agent orchestration.

The service owns the bounded host loop. Providers return one NextDecision at a time;
the host validates every decision against the effective CapabilityRegistry views and
executes only REASONING capabilities directly. PLAN proposals remain stage-only.
"""

from __future__ import annotations

import inspect
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
from .budgets import AgentBudgetError, resolve_agent_budgets
from .contracts import (
    FinalAnswer,
    NextDecision,
    PlanStepProposal,
    ReasoningCapabilityCall,
    TaskPlanUpdate,
    decision_payload,
)
from .decision_validation import NextDecisionValidationError, validate_next_decision
from .task_plan import TaskPlan, TaskPlanError, parse_task_plan
from .working_transcript import (
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
    step_id: str = ""
    depends_on: tuple[str, ...] = ()


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
    task_plan: TaskPlan | None = None


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

    Provider adapters remain intentionally thin. The service owns task/effect-plan accumulation,
    budgets, validation and orchestration so future providers can implement ``NextDecisionEngine``
    without duplicating Odoo authority or effect semantics.
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
        try:
            budgets = resolve_agent_budgets(self._context)
        except AgentBudgetError as error:
            raise AgentTurnError(error.code) from error
        await self._ensure_user_input(message)
        resumed = self._resume_terminal(planning)
        if resumed is not None:
            return resumed
        await self._close_interrupted_calls()

        provider_decisions = _provider_decisions_used(self._working_items)
        capability_calls = _capability_calls_used(self._working_items)
        consecutive_failures = _trailing_failure_count(self._working_items)
        terminal_error = _terminal_error_pending(self._working_items)

        while provider_decisions < budgets.provider_decision_limit:
            self._ensure_not_cancelled()
            effect_steps = (
                len(_proposed_plan(self._working_items))
                if self._allow_plan_proposals
                else 0
            )
            remaining = budgets.remaining(
                provider_decisions=provider_decisions,
                capability_calls=capability_calls,
                consecutive_failures=consecutive_failures,
                transcript_bytes=working_transcript_bytes(self._working_items),
                effect_steps=effect_steps,
            )
            decision_counted = False
            try:
                decision = await engine.next_decision(
                    message=message,
                    conversation_summary=conversation_summary,
                    context=self._context,
                    reasoning_capabilities=reasoning,
                    planning_capabilities=planning,
                    working_items=tuple(item.payload() for item in self._working_items),
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
                if not isinstance(
                    rejected,
                    (ReasoningCapabilityCall, PlanStepProposal, TaskPlanUpdate),
                ):
                    raise AgentTurnError(error.code) from error
                if isinstance(rejected, ReasoningCapabilityCall):
                    capability_calls += 1
                    if capability_calls > budgets.exploration.max_capability_calls:
                        raise AgentTurnError("agent_capability_call_budget_exceeded") from error
                if isinstance(rejected, TaskPlanUpdate):
                    await self._record_rejected_task_plan(rejected.task_plan, error.code)
                else:
                    await self._record_rejected_decision(rejected, error.code)
                consecutive_failures += 1
                if consecutive_failures > budgets.safety.max_consecutive_failures:
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
                proposed = _proposed_plan(self._working_items) if self._allow_plan_proposals else ()
                plan = self._validate_plan(proposed, planning) if proposed else ()
                return AgentTurnResult(
                    answer=answer,
                    confidence=decision.confidence,
                    plan=plan,
                    task_plan=_latest_task_plan(self._working_items),
                )

            if isinstance(decision, TaskPlanUpdate):
                # TaskPlan is progress data only. It cannot erase a failing capability streak or
                # clear a terminal authority/policy error, otherwise a provider could use harmless
                # plan revisions to evade safety budgets.
                await self._record_task_plan(decision.task_plan)
                continue

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
                current = _proposed_plan(self._working_items)
                if len(current) >= budgets.safety.max_effect_steps:
                    self._working_items = append_working_item(
                        self._working_items,
                        "capability_error",
                        {
                            "call_id": decision.call_id,
                            "capability": decision.capability,
                            "code": "agent_plan_limit_exceeded",
                        },
                    )
                    await self._persist()
                    raise AgentTurnError("agent_plan_limit_exceeded")
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
                consecutive_failures = 0
                terminal_error = False
                if budgets.safety.max_effect_steps == 1:
                    plan = self._validate_plan(_proposed_plan(self._working_items), planning)
                    return AgentTurnResult(
                        answer="He preparado la acción solicitada para revisión.",
                        confidence="high",
                        plan=plan,
                        task_plan=_latest_task_plan(self._working_items),
                    )
                continue

            if not isinstance(decision, ReasoningCapabilityCall):
                raise AgentTurnError("agent_next_decision_invalid")

            capability_calls += 1
            if capability_calls > budgets.exploration.max_capability_calls:
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
                if consecutive_failures > budgets.safety.max_consecutive_failures:
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
                    or consecutive_failures > budgets.safety.max_consecutive_failures
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
                if consecutive_failures > budgets.safety.max_consecutive_failures:
                    raise AgentTurnError("agent_correctable_failure_budget_exceeded")
                continue
            await self._persist()
            consecutive_failures = 0
            terminal_error = False

        raise AgentTurnError("agent_provider_decision_budget_exceeded")

    async def _record_task_plan(self, plan: TaskPlan) -> None:
        previous = _latest_task_plan(self._working_items)
        expected_revision = 1 if previous is None else previous.revision + 1
        if plan.revision != expected_revision:
            raise AgentTurnError("agent_task_plan_revision_invalid")
        self._working_items = append_working_item(
            self._working_items,
            "task_plan",
            plan.payload(),
        )
        await self._persist()
        self._context.emit(
            "task_plan.updated",
            "Plan de trabajo actualizado",
            {
                "revision": plan.revision,
                "step_count": len(plan.steps),
            },
        )

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

    async def _record_rejected_task_plan(self, plan: TaskPlan, code: str) -> None:
        self._working_items = append_working_item(
            self._working_items,
            "task_plan_error",
            {"code": code, "rejected_revision": plan.revision},
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

    def _resume_terminal(
        self,
        planning: tuple[CapabilityDefinition, ...],
    ) -> AgentTurnResult | None:
        if not self._working_items:
            return None
        last = self._working_items[-1]
        if last.kind != "final_answer":
            return None
        answer = last.data.get("answer")
        confidence = last.data.get("confidence")
        if not isinstance(answer, str) or not isinstance(confidence, str):
            raise AgentTurnError("agent_working_transcript_invalid")
        proposed = _proposed_plan(self._working_items) if self._allow_plan_proposals else ()
        plan = self._validate_plan(proposed, planning) if proposed else ()
        return AgentTurnResult(
            answer=_validated_answer(answer, confidence),
            confidence=confidence,
            plan=plan,
            task_plan=_latest_task_plan(self._working_items),
        )

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
        try:
            budgets = resolve_agent_budgets(self._context)
        except AgentBudgetError as error:
            raise AgentTurnError(error.code) from error
        if not isinstance(plan, tuple) or len(plan) > budgets.safety.max_effect_steps:
            raise AgentTurnError("agent_plan_limit_exceeded")
        allowed = {definition.name: definition for definition in planning}
        normalized: list[PlannedCapability] = []
        seen_step_ids: set[str] = set()
        for position, step in enumerate(plan):
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
            step_id = step.step_id or f"step-{position + 1}"
            if not isinstance(step_id, str) or not step_id or len(step_id) > 256:
                raise AgentTurnError("agent_plan_invalid")
            depends_on = tuple(step.depends_on)
            if any(dep not in seen_step_ids for dep in depends_on):
                raise AgentTurnError("agent_plan_dependency_invalid")
            if step_id in seen_step_ids:
                raise AgentTurnError("agent_plan_dependency_invalid")
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
                    step_id=step_id,
                    depends_on=depends_on,
                )
            )
            seen_step_ids.add(step_id)
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


def _latest_task_plan(items: tuple[WorkingItem, ...]) -> TaskPlan | None:
    for item in reversed(items):
        if item.kind != "task_plan":
            continue
        try:
            return parse_task_plan(dict(item.data))
        except TaskPlanError as error:
            raise AgentTurnError(error.code) from error
    return None


def _proposed_plan(items: tuple[WorkingItem, ...]) -> tuple[PlannedCapability, ...]:
    proposed = [item for item in items if item.kind == "plan_step_proposed"]
    result: list[PlannedCapability] = []
    previous_step_id: str | None = None
    for item in proposed:
        call_id = item.data.get("call_id")
        capability = item.data.get("capability")
        arguments = item.data.get("arguments")
        summary = item.data.get("user_summary")
        if (
            not isinstance(call_id, str)
            or not isinstance(capability, str)
            or not isinstance(arguments, dict)
            or not isinstance(summary, str)
        ):
            raise AgentTurnError("agent_working_transcript_invalid")
        result.append(
            PlannedCapability(
                capability=capability,
                arguments=dict(arguments),
                summary=summary,
                step_id=call_id,
                depends_on=((previous_step_id,) if previous_step_id is not None else ()),
            )
        )
        previous_step_id = call_id
    return tuple(result)


def _provider_decisions_used(items: tuple[WorkingItem, ...]) -> int:
    return sum(
        item.kind in {"assistant_decision", "task_plan", "task_plan_error", "final_answer"}
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
        if item.kind in {"capability_error", "task_plan_error"}:
            count += 1
            continue
        if item.kind == "capability_result":
            return 0
        if item.kind in {
            "assistant_decision",
            "capability_call",
            "plan_step_proposed",
            "task_plan",
        }:
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
