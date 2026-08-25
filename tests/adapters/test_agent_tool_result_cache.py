import asyncio

import pytest
from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.adapters.agent_timing import TimedToolExecutor
from odoo_ai.contracts import ToolRisk, ToolSpec, TurnLimits
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: int = Field(strict=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: int = Field(strict=True)
    calls: int = Field(strict=True, ge=1)


def _binding(name, handler):
    spec = ToolSpec(
        name=name,
        description="test tool",
        input_schema=InputModel.model_json_schema(),
        risk=ToolRisk.METADATA,
        executor_id=f"{name}.v1",
    )
    return RegisteredTool(
        spec=spec,
        executor_id=spec.executor_id,
        input_model=InputModel,
        output_model=OutputModel,
        handler=handler,
    )


def _executor(*bindings):
    return TimedToolExecutor(
        registry=ToolRegistry(bindings),
        ledger=EvidenceLedger(max_items=0, max_payload_bytes=1024),
        turn_limits=TurnLimits(max_tool_calls=12, max_evidence_items=0),
        limits=ToolExecutionLimits(
            max_calls=12,
            max_evidence_items=0,
            max_evidence_bytes=1024,
        ),
    )


def test_identical_successful_call_is_reused_without_consuming_another_execution() -> None:
    calls = 0

    async def handler(value):
        nonlocal calls
        calls += 1
        return ToolHandlerOutput(data={"value": value.value, "calls": calls})

    executor = _executor(_binding("test.read", handler))
    first = asyncio.run(
        executor.execute(
            ToolCall(call_id="call-1", tool_name="test.read", arguments={"value": 7})
        )
    )
    second = asyncio.run(
        executor.execute(
            ToolCall(call_id="call-2", tool_name="test.read", arguments={"value": 7})
        )
    )

    assert first.data == {"value": 7, "calls": 1}
    assert second.data == first.data
    assert second.call_id == "call-2"
    assert calls == 1
    assert len(executor.execution_events) == 2


def test_precondition_revision_invalidates_cached_result() -> None:
    read_calls = 0
    refresh_calls = 0

    async def read_handler(value):
        nonlocal read_calls
        read_calls += 1
        return ToolHandlerOutput(data={"value": value.value, "calls": read_calls})

    async def refresh_handler(value):
        nonlocal refresh_calls
        refresh_calls += 1
        return ToolHandlerOutput(
            data={"value": value.value, "calls": refresh_calls},
            changes_preconditions=True,
        )

    executor = _executor(
        _binding("test.read", read_handler),
        _binding("test.refresh", refresh_handler),
    )
    asyncio.run(
        executor.execute(
            ToolCall(call_id="read-1", tool_name="test.read", arguments={"value": 4})
        )
    )
    asyncio.run(
        executor.execute(
            ToolCall(
                call_id="refresh-1",
                tool_name="test.refresh",
                arguments={"value": 1},
            )
        )
    )
    result = asyncio.run(
        executor.execute(
            ToolCall(call_id="read-2", tool_name="test.read", arguments={"value": 4})
        )
    )

    assert result.data == {"value": 4, "calls": 2}
    assert read_calls == 2
    assert refresh_calls == 1


def test_cache_hit_does_not_allow_duplicate_call_id() -> None:
    async def handler(value):
        return ToolHandlerOutput(data={"value": value.value, "calls": 1})

    executor = _executor(_binding("test.read", handler))
    call = ToolCall(call_id="same-id", tool_name="test.read", arguments={"value": 9})
    asyncio.run(executor.execute(call))

    with pytest.raises(ToolExecutorError, match="tool_call_duplicate"):
        asyncio.run(executor.execute(call))
