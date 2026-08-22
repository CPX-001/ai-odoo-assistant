import asyncio
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    ToolRisk,
    ToolSpec,
    TurnLimits,
)
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

EVIDENCE_ID = UUID("12345678-1234-5678-1234-567812345678")
OTHER_EVIDENCE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str = Field(min_length=1, max_length=2_000)


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    echoed: str = Field(max_length=2_000)


def _evidence(
    evidence_id: UUID = EVIDENCE_ID, *, summary: str = "Checked fixture."
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        kind=EvidenceKind.METADATA,
        status=EvidenceStatus.CHECKED,
        title="Fixture evidence",
        summary=summary,
        payload={"safe": True},
        sensitivity=EvidenceSensitivity.NORMAL,
    )


def _spec(
    *,
    name: str = "fixture.echo",
    executor_id: str = "fixture.echo.v1",
    risk: ToolRisk = ToolRisk.READ,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Echo one validated string.",
        input_schema=EchoInput.model_json_schema(),
        risk=risk,
        executor_id=executor_id,
    )


def _binding(
    handler,
    *,
    spec: ToolSpec | None = None,
    executor_id: str = "fixture.echo.v1",
    max_calls: int = 4,
    max_output_bytes: int = 96 * 1024,
) -> RegisteredTool:
    return RegisteredTool(
        spec=spec or _spec(),
        executor_id=executor_id,
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=handler,
        max_calls=max_calls,
        max_output_bytes=max_output_bytes,
    )


def _executor(
    binding: RegisteredTool,
    *,
    max_tool_calls: int = 4,
    ledger: EvidenceLedger | None = None,
    limits: ToolExecutionLimits | None = None,
    clock=None,
) -> ToolExecutor:
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    return ToolExecutor(
        registry=ToolRegistry([binding]),
        ledger=ledger or EvidenceLedger(max_items=8, max_payload_bytes=32 * 1024),
        turn_limits=TurnLimits(max_tool_calls=max_tool_calls, max_evidence_items=8),
        limits=limits,
        **kwargs,
    )


def test_explicit_registry_happy_path_validates_output_and_adds_evidence() -> None:
    calls: list[str] = []

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        validated = EchoInput.model_validate(value)
        calls.append(validated.value)
        return ToolHandlerOutput(
            data={"echoed": validated.value},
            evidence=(_evidence(),),
        )

    executor = _executor(_binding(handler))
    result = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="call-1",
                tool_name="fixture.echo",
                arguments={"value": "hello"},
            )
        )
    )

    assert calls == ["hello"]
    assert result.data == {"echoed": "hello"}
    assert result.evidence == (_evidence(),)
    assert executor.ledger.resolve_refs([EVIDENCE_ID]) == (_evidence(),)


def test_unknown_tool_is_rejected_without_running_handler() -> None:
    calls = 0

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        nonlocal calls
        calls += 1
        return ToolHandlerOutput(data={"echoed": "unused"})

    executor = _executor(_binding(handler))
    with pytest.raises(ToolExecutorError, match="tool_not_registered"):
        asyncio.run(
            executor.execute(
                ToolCall(call_id="call-1", tool_name="fixture.unknown", arguments={})
            )
        )
    assert calls == 0


def test_executor_id_and_input_schema_must_match_explicit_binding() -> None:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        return ToolHandlerOutput(data={"echoed": "unused"})

    with pytest.raises(ToolExecutorError, match="tool_executor_id_mismatch"):
        _binding(handler, executor_id="attacker.executor")
    manipulated = _spec().model_copy(update={"input_schema": {"type": "object"}})
    with pytest.raises(ToolExecutorError, match="tool_input_schema_mismatch"):
        _binding(handler, spec=manipulated)


@pytest.mark.parametrize(
    "risk", [ToolRisk.WRITE, ToolRisk.ACTION, ToolRisk.WRITE_PREVIEW]
)
def test_non_read_risks_are_rejected(risk: ToolRisk) -> None:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        return ToolHandlerOutput(data={"echoed": "unused"})

    with pytest.raises(ToolExecutorError, match="tool_risk_not_allowed"):
        _binding(handler, spec=_spec(risk=risk))


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"value": "ok", "extra": "forbidden"},
        {"value": 3},
    ],
)
def test_invalid_or_extra_input_is_rejected(arguments: dict[str, object]) -> None:
    calls = 0

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        nonlocal calls
        calls += 1
        return ToolHandlerOutput(data={"echoed": "unused"})

    executor = _executor(_binding(handler))
    with pytest.raises(ToolExecutorError, match="tool_input_invalid"):
        asyncio.run(
            executor.execute(
                ToolCall.model_construct(
                    call_id="call-1", tool_name="fixture.echo", arguments=arguments
                )
            )
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("handler_result", "max_output_bytes", "error_code"),
    [
        (ToolHandlerOutput(data={"wrong": "shape"}), 1024, "tool_output_invalid"),
        (
            ToolHandlerOutput(data={"echoed": "x" * 500}),
            256,
            "tool_output_too_large",
        ),
    ],
)
def test_invalid_or_oversized_output_is_rejected(
    handler_result: ToolHandlerOutput,
    max_output_bytes: int,
    error_code: str,
) -> None:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        return handler_result

    executor = _executor(_binding(handler, max_output_bytes=max_output_bytes))
    with pytest.raises(ToolExecutorError, match=error_code):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="call-1",
                    tool_name="fixture.echo",
                    arguments={"value": "valid"},
                )
            )
        )


def test_call_and_duplicate_budgets_fail_closed() -> None:
    calls = 0

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        nonlocal calls
        calls += 1
        validated = EchoInput.model_validate(value)
        return ToolHandlerOutput(data={"echoed": validated.value})

    executor = _executor(_binding(handler), max_tool_calls=1)
    first = ToolCall(
        call_id="call-1", tool_name="fixture.echo", arguments={"value": "one"}
    )
    asyncio.run(executor.execute(first))
    with pytest.raises(ToolExecutorError, match="tool_call_duplicate"):
        asyncio.run(executor.execute(first))
    with pytest.raises(ToolExecutorError, match="tool_call_budget_exceeded"):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="call-2",
                    tool_name="fixture.echo",
                    arguments={"value": "two"},
                )
            )
        )
    assert calls == 1


def test_deadline_is_checked_before_handler() -> None:
    now = [10.0]
    calls = 0

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        nonlocal calls
        calls += 1
        return ToolHandlerOutput(data={"echoed": "unused"})

    limits = ToolExecutionLimits(deadline_seconds=1)
    executor = _executor(_binding(handler), limits=limits, clock=lambda: now[0])
    now[0] = 11.0
    with pytest.raises(ToolExecutorError, match="tool_deadline_exceeded"):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="call-1",
                    tool_name="fixture.echo",
                    arguments={"value": "late"},
                )
            )
        )
    assert calls == 0


def test_evidence_duplicate_conflict_and_item_cap_are_atomic() -> None:
    ledger = EvidenceLedger(
        max_items=2,
        max_payload_bytes=32 * 1024,
        live=[_evidence()],
    )
    with pytest.raises(ToolExecutorError, match="evidence_duplicate_conflict"):
        ledger.add_retrieved([_evidence(summary="Conflicting content.")])
    assert ledger.evidence_ids == {EVIDENCE_ID}

    ledger.add_retrieved([_evidence(OTHER_EVIDENCE_ID)])
    third = _evidence(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    with pytest.raises(ToolExecutorError, match="evidence_item_budget_exceeded"):
        ledger.add_retrieved([third])
    assert ledger.evidence_ids == {EVIDENCE_ID, OTHER_EVIDENCE_ID}


def test_invented_final_evidence_ref_is_rejected() -> None:
    ledger = EvidenceLedger(
        max_items=2,
        max_payload_bytes=32 * 1024,
        live=[_evidence()],
    )
    with pytest.raises(ToolExecutorError, match="evidence_ref_unknown"):
        ledger.resolve_refs([OTHER_EVIDENCE_ID])


def test_executor_rejects_ledger_cap_larger_than_turn_limit() -> None:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        return ToolHandlerOutput(data={"echoed": "unused"})

    with pytest.raises(ToolExecutorError, match="evidence_ledger_exceeds_turn_limit"):
        ToolExecutor(
            registry=ToolRegistry([_binding(handler)]),
            ledger=EvidenceLedger(max_items=2, max_payload_bytes=32 * 1024),
            turn_limits=TurnLimits(max_tool_calls=1, max_evidence_items=1),
        )
