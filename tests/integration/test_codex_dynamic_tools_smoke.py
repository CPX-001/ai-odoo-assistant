"""Opt-in real App Server dynamic-tool roundtrip with a synthetic backend."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from odoo_ai.adapters import (
    SOURCE_FIND_SYMBOL,
    CodexAppServerEngine,
    CodexRuntimeSettings,
    build_source_tool_registry,
    source_tool_specs,
)
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    FindModelExtensionsRequest,
    FindModelExtensionsResult,
    FindSymbolRequest,
    FindSymbolResult,
    InstanceProfileSummary,
    ReadExcerptRequest,
    ScreenContext,
    SourceExcerpt,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)
from odoo_ai.tools import EvidenceLedger, ToolExecutionLimits, ToolExecutor


class SyntheticSourceBackend:
    def __init__(self) -> None:
        self.requests: list[FindSymbolRequest] = []

    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult:
        self.requests.append(request)
        return FindSymbolResult(candidates=())

    async def find_model_extensions(
        self, request: FindModelExtensionsRequest
    ) -> FindModelExtensionsResult:
        raise AssertionError("tool was not advertised")

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt:
        raise AssertionError("tool was not advertised")


def _factory(backend: SyntheticSourceBackend):
    @asynccontextmanager
    async def factory(context: ContextPack, tools):
        limits = ToolExecutionLimits()
        yield ToolExecutor(
            registry=build_source_tool_registry(backend, tools),
            ledger=EvidenceLedger(
                max_items=context.limits.max_evidence_items,
                max_payload_bytes=limits.max_evidence_bytes,
            ),
            turn_limits=context.limits,
            limits=limits,
        )

    return factory


@pytest.mark.skipif(
    not os.environ.get("ODOO_AI_RUN_CODEX_DYNAMIC_TOOLS_SMOKE"),
    reason="real authenticated Codex dynamic-tool smoke is opt-in",
)
def test_real_codex_requests_one_registered_dynamic_tool() -> None:
    backend = SyntheticSourceBackend()
    screen = ScreenContext(
        model="sale.order",
        res_id=56,
        captured_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
    )
    context = ContextPack(
        request=UserRequest(
            message=(
                "Before answering, call source.find_symbol exactly once with query "
                "action_confirm, model sale.order, and max_results 1. Then explain that "
                "the synthetic index returned no candidates."
            )
        ),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1),
        workflow_hint=Workflow.EXPLAIN,
        instance=InstanceProfileSummary(
            instance_id="synthetic-dynamic-smoke",
            capabilities=["source"],
        ),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=2, max_evidence_items=2),
    )
    find_symbol_spec = next(spec for spec in source_tool_specs() if spec.name == SOURCE_FIND_SYMBOL)
    engine = CodexAppServerEngine(
        CodexRuntimeSettings.from_env(),
        tool_executor_factory=_factory(backend),
    )

    answer = asyncio.run(
        engine.run_turn(
            context,
            [find_symbol_spec],
            AnswerEnvelope.model_json_schema(),
        )
    )

    assert answer.workflow is Workflow.EXPLAIN
    assert answer.proposed_action is None
    assert len(backend.requests) == 1
    assert backend.requests[0] == FindSymbolRequest(
        query="action_confirm",
        model="sale.order",
        max_results=1,
    )
