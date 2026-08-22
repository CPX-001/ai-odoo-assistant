"""Per-turn allowlisted tool execution, budgets, and evidence ledger."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from odoo_ai.contracts import Evidence, ToolExecutionEvent, ToolRisk, ToolSpec, TurnLimits

ToolHandler = Callable[[BaseModel], Awaitable["ToolHandlerOutput"]]
Clock = Callable[[], float]
_ALLOWED_RISKS = frozenset({ToolRisk.READ, ToolRisk.METADATA})


class ToolExecutorError(RuntimeError):
    """Sanitized host-side tool failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ToolCall(BaseModel):
    """One untrusted tool request received from a reasoning provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    tool_name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    arguments: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolHandlerOutput:
    """Raw handler output that the executor must validate before release."""

    data: object
    evidence: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidatedToolResult:
    """Bounded result safe to serialize back to the reasoning provider."""

    call_id: str
    tool_name: str
    data: dict[str, JsonValue]
    evidence: tuple[Evidence, ...]

    def wire_value(self) -> dict[str, JsonValue]:
        return {
            "ok": True,
            "call_id": self.call_id,
            "data": self.data,
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Explicit binding between one advertised spec and one concrete handler."""

    spec: ToolSpec
    executor_id: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler
    max_calls: int = 4
    max_input_bytes: int = 16 * 1024
    max_output_bytes: int = 96 * 1024

    def __post_init__(self) -> None:
        if not self.executor_id or len(self.executor_id) > 128:
            raise ToolExecutorError("tool_executor_id_invalid")
        if self.spec.executor_id != self.executor_id:
            raise ToolExecutorError("tool_executor_id_mismatch")
        if self.spec.risk not in _ALLOWED_RISKS:
            raise ToolExecutorError("tool_risk_not_allowed")
        if not 1 <= self.max_calls <= 64:
            raise ToolExecutorError("tool_call_limit_invalid")
        if not 256 <= self.max_input_bytes <= 1024 * 1024:
            raise ToolExecutorError("tool_input_limit_invalid")
        if not 256 <= self.max_output_bytes <= 4 * 1024 * 1024:
            raise ToolExecutorError("tool_output_limit_invalid")
        if _canonical_json(self.spec.input_schema) != _canonical_json(
            self.input_model.model_json_schema()
        ):
            raise ToolExecutorError("tool_input_schema_mismatch")


class ToolRegistry:
    """Immutable explicit registry constructed for one turn."""

    def __init__(self, bindings: Iterable[RegisteredTool]) -> None:
        by_name: dict[str, RegisteredTool] = {}
        executor_ids: set[str] = set()
        for binding in bindings:
            if binding.spec.name in by_name:
                raise ToolExecutorError("tool_name_duplicate")
            if binding.executor_id in executor_ids:
                raise ToolExecutorError("tool_executor_id_duplicate")
            by_name[binding.spec.name] = binding
            executor_ids.add(binding.executor_id)
        self._by_name = by_name

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(binding.spec for binding in self._by_name.values())

    def resolve(self, name: str) -> RegisteredTool:
        binding = self._by_name.get(name)
        if binding is None:
            raise ToolExecutorError("tool_not_registered")
        return binding


class EvidenceOrigin(StrEnum):
    LIVE = "live"
    RETRIEVED = "retrieved"


class EvidenceLedger:
    """Ephemeral per-turn index of host-validated evidence."""

    def __init__(
        self,
        *,
        max_items: int,
        max_payload_bytes: int,
        live: Iterable[Evidence] = (),
        retrieved: Iterable[Evidence] = (),
    ) -> None:
        if not 0 <= max_items <= 512:
            raise ToolExecutorError("evidence_limit_invalid")
        if not 1024 <= max_payload_bytes <= 8 * 1024 * 1024:
            raise ToolExecutorError("evidence_bytes_limit_invalid")
        self._max_items = max_items
        self._max_payload_bytes = max_payload_bytes
        self._items: dict[UUID, Evidence] = {}
        self._origins: dict[UUID, EvidenceOrigin] = {}
        self._canonical: dict[UUID, bytes] = {}
        self._payload_bytes = 0
        self._add_many(tuple(live), EvidenceOrigin.LIVE)
        self._add_many(tuple(retrieved), EvidenceOrigin.RETRIEVED)

    @property
    def live_evidence(self) -> tuple[Evidence, ...]:
        return tuple(
            item
            for evidence_id, item in self._items.items()
            if self._origins[evidence_id] is EvidenceOrigin.LIVE
        )

    @property
    def max_items(self) -> int:
        return self._max_items

    @property
    def max_payload_bytes(self) -> int:
        return self._max_payload_bytes

    @property
    def retrieved_evidence(self) -> tuple[Evidence, ...]:
        return tuple(
            item
            for evidence_id, item in self._items.items()
            if self._origins[evidence_id] is EvidenceOrigin.RETRIEVED
        )

    @property
    def evidence_ids(self) -> frozenset[UUID]:
        return frozenset(self._items)

    def add_retrieved(self, evidence: Iterable[Evidence]) -> tuple[Evidence, ...]:
        validated = tuple(Evidence.model_validate(item) for item in evidence)
        self._add_many(validated, EvidenceOrigin.RETRIEVED)
        return validated

    def resolve_refs(self, references: Sequence[UUID]) -> tuple[Evidence, ...]:
        try:
            return tuple(self._items[reference] for reference in references)
        except KeyError:
            raise ToolExecutorError("evidence_ref_unknown") from None

    def _add_many(self, evidence: tuple[Evidence, ...], origin: EvidenceOrigin) -> None:
        pending: dict[UUID, tuple[Evidence, bytes]] = {}
        for item in evidence:
            canonical = _canonical_bytes(item.model_dump(mode="json"))
            known = self._canonical.get(item.evidence_id)
            if known is not None:
                if known != canonical:
                    raise ToolExecutorError("evidence_duplicate_conflict")
                continue
            pending_known = pending.get(item.evidence_id)
            if pending_known is not None:
                if pending_known[1] != canonical:
                    raise ToolExecutorError("evidence_duplicate_conflict")
                continue
            pending[item.evidence_id] = (item, canonical)
        if len(self._items) + len(pending) > self._max_items:
            raise ToolExecutorError("evidence_item_budget_exceeded")
        new_bytes = sum(len(canonical) for _, canonical in pending.values())
        if self._payload_bytes + new_bytes > self._max_payload_bytes:
            raise ToolExecutorError("evidence_bytes_budget_exceeded")
        for evidence_id, (item, canonical) in pending.items():
            self._items[evidence_id] = item
            self._origins[evidence_id] = origin
            self._canonical[evidence_id] = canonical
        self._payload_bytes += new_bytes


@dataclass(frozen=True, slots=True)
class ToolExecutionLimits:
    """Server-enforced aggregate budgets for one executor instance."""

    max_calls: int = 12
    max_total_input_bytes: int = 64 * 1024
    max_total_output_bytes: int = 256 * 1024
    max_evidence_items: int = 24
    max_evidence_bytes: int = 192 * 1024
    max_input_nesting: int = 8
    deadline_seconds: float = 30.0
    per_tool_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not 0 <= self.max_calls <= 128:
            raise ToolExecutorError("tool_total_call_limit_invalid")
        if not 1024 <= self.max_total_input_bytes <= 8 * 1024 * 1024:
            raise ToolExecutorError("tool_total_input_limit_invalid")
        if not 1024 <= self.max_total_output_bytes <= 32 * 1024 * 1024:
            raise ToolExecutorError("tool_total_output_limit_invalid")
        if not 0 <= self.max_evidence_items <= 512:
            raise ToolExecutorError("tool_evidence_item_limit_invalid")
        if not 1024 <= self.max_evidence_bytes <= 8 * 1024 * 1024:
            raise ToolExecutorError("tool_evidence_bytes_limit_invalid")
        if not 1 <= self.max_input_nesting <= 32:
            raise ToolExecutorError("tool_nesting_limit_invalid")
        if not 0 < self.deadline_seconds <= 600:
            raise ToolExecutorError("tool_deadline_invalid")
        if not 0 < self.per_tool_timeout_seconds <= 120:
            raise ToolExecutorError("tool_timeout_invalid")


class ToolExecutor:
    """Validate and execute only handlers bound explicitly for this turn."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        ledger: EvidenceLedger,
        turn_limits: TurnLimits,
        limits: ToolExecutionLimits | None = None,
        clock: Clock = monotonic,
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._limits = limits or ToolExecutionLimits()
        if ledger.max_items > turn_limits.max_evidence_items:
            raise ToolExecutorError("evidence_ledger_exceeds_turn_limit")
        if ledger.max_items > self._limits.max_evidence_items:
            raise ToolExecutorError("evidence_ledger_exceeds_host_limit")
        if ledger.max_payload_bytes > self._limits.max_evidence_bytes:
            raise ToolExecutorError("evidence_ledger_bytes_exceed_host_limit")
        self._max_calls = min(turn_limits.max_tool_calls, self._limits.max_calls)
        self._clock = clock
        self._deadline = clock() + self._limits.deadline_seconds
        self._seen_call_ids: set[str] = set()
        self._tool_calls: dict[str, int] = {}
        self._calls = 0
        self._input_bytes = 0
        self._output_bytes = 0
        self._events: list[ToolExecutionEvent] = []

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    @property
    def execution_events(self) -> tuple[ToolExecutionEvent, ...]:
        return tuple(self._events)

    async def execute(self, call: ToolCall) -> ValidatedToolResult:
        self._events.append(
            ToolExecutionEvent(
                event_name="tool.requested",
                status="ok",
                attributes={"tool_name": call.tool_name},
            )
        )
        try:
            result = await self._execute(call)
        except ToolExecutorError as error:
            self._events.append(
                ToolExecutionEvent(
                    event_name="tool.completed",
                    status="error",
                    attributes={
                        "error_code": error.code,
                        "tool_name": call.tool_name,
                    },
                )
            )
            raise
        self._events.append(
            ToolExecutionEvent(
                event_name="tool.completed",
                status="ok",
                attributes={
                    "evidence_count": len(result.evidence),
                    "tool_name": call.tool_name,
                },
            )
        )
        return result

    async def _execute(self, call: ToolCall) -> ValidatedToolResult:
        if call.call_id in self._seen_call_ids:
            raise ToolExecutorError("tool_call_duplicate")
        binding = self._registry.resolve(call.tool_name)
        if binding.spec.risk not in _ALLOWED_RISKS:
            raise ToolExecutorError("tool_risk_not_allowed")
        _validate_nesting(call.arguments, self._limits.max_input_nesting)
        input_bytes = _canonical_bytes(call.arguments)
        if len(input_bytes) > binding.max_input_bytes:
            raise ToolExecutorError("tool_input_too_large")
        if self._input_bytes + len(input_bytes) > self._limits.max_total_input_bytes:
            raise ToolExecutorError("tool_input_budget_exceeded")
        try:
            validated_input = binding.input_model.model_validate(call.arguments)
        except ValidationError:
            raise ToolExecutorError("tool_input_invalid") from None
        if self._clock() >= self._deadline:
            raise ToolExecutorError("tool_deadline_exceeded")
        if self._calls >= self._max_calls:
            raise ToolExecutorError("tool_call_budget_exceeded")
        per_tool_calls = self._tool_calls.get(call.tool_name, 0)
        if per_tool_calls >= binding.max_calls:
            raise ToolExecutorError("tool_per_name_budget_exceeded")

        self._seen_call_ids.add(call.call_id)
        self._calls += 1
        self._tool_calls[call.tool_name] = per_tool_calls + 1
        self._input_bytes += len(input_bytes)
        total_remaining = self._deadline - self._clock()
        remaining = min(total_remaining, self._limits.per_tool_timeout_seconds)
        if remaining <= 0:
            raise ToolExecutorError("tool_deadline_exceeded")
        try:
            async with asyncio.timeout(remaining):
                raw_result = await binding.handler(validated_input)
        except TimeoutError:
            code = (
                "tool_deadline_exceeded"
                if total_remaining <= self._limits.per_tool_timeout_seconds
                else "tool_timeout_exceeded"
            )
            raise ToolExecutorError(code) from None
        except ToolExecutorError:
            raise
        except Exception:
            raise ToolExecutorError("tool_handler_failed") from None
        if self._clock() > self._deadline:
            raise ToolExecutorError("tool_deadline_exceeded")
        if not isinstance(raw_result, ToolHandlerOutput):
            raise ToolExecutorError("tool_output_invalid")
        try:
            output_model = binding.output_model.model_validate(raw_result.data)
            evidence = tuple(Evidence.model_validate(item) for item in raw_result.evidence)
        except ValidationError:
            raise ToolExecutorError("tool_output_invalid") from None
        data = cast(dict[str, JsonValue], output_model.model_dump(mode="json"))
        result = ValidatedToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            data=data,
            evidence=evidence,
        )
        output_bytes = _canonical_bytes(result.wire_value())
        if len(output_bytes) > binding.max_output_bytes:
            raise ToolExecutorError("tool_output_too_large")
        if self._output_bytes + len(output_bytes) > self._limits.max_total_output_bytes:
            raise ToolExecutorError("tool_output_budget_exceeded")
        self._ledger.add_retrieved(evidence)
        self._output_bytes += len(output_bytes)
        return result


def _validate_nesting(value: object, max_depth: int, *, depth: int = 0) -> None:
    if depth > max_depth:
        raise ToolExecutorError("tool_input_nested_too_deep")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ToolExecutorError("tool_input_invalid")
            _validate_nesting(item, max_depth, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_nesting(item, max_depth, depth=depth + 1)


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise ToolExecutorError("tool_json_invalid") from None


def _canonical_bytes(value: object) -> bytes:
    return _canonical_json(value).encode("utf-8")
