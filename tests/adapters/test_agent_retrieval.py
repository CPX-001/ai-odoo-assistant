import asyncio
from datetime import UTC, datetime

import pytest

from odoo_ai.adapters.agent_retrieval import (
    AgentRetrievalBindingFactory,
    agent_retrieval_tool_specs,
)
from odoo_ai.adapters.knowledge_tools import KNOWLEDGE_SEARCH, KnowledgeToolBackend
from odoo_ai.adapters.source_tools import SOURCE_FIND_SYMBOL
from odoo_ai.contracts import (
    ContextPack,
    ConversationState,
    InstanceProfileSummary,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    ScreenContext,
    ToolRisk,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)
from odoo_ai.ports import OdooGatewayError
from odoo_ai.tools import (
    EvidenceLedger,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolRegistry,
)

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


class FakeKnowledgeBackend(KnowledgeToolBackend):
    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        assert request.query == "payment terms"
        return KnowledgeSearchResult(candidates=(), truncated=False)

    async def read_excerpt(self, request):
        raise AssertionError(f"unexpected read: {request}")


def _context() -> ContextPack:
    screen = ScreenContext(model="res.partner", view_type="form", captured_at=NOW)
    return ContextPack(
        request=UserRequest(message="How do I configure payment terms?"),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1, allowed_company_ids=[1]),
        workflow_hint=None,
        instance=InstanceProfileSummary(instance_id="test-instance"),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=8, max_evidence_items=8),
    )


def _executor(factory: AgentRetrievalBindingFactory) -> ToolExecutor:
    context = _context()
    bindings = factory(context, agent_retrieval_tool_specs())
    return ToolExecutor(
        registry=ToolRegistry(
            bindings,
            allowed_risks={ToolRisk.READ, ToolRisk.METADATA},
        ),
        ledger=EvidenceLedger(max_items=8, max_payload_bytes=64 * 1024),
        turn_limits=context.limits,
        limits=ToolExecutionLimits(max_calls=8),
    )


def test_knowledge_search_is_empty_without_preparing_source_runtime() -> None:
    inventory_calls = 0

    def unavailable_sessions():
        raise AssertionError("fake knowledge backend must not open a DB session")

    def inventory_loader():
        nonlocal inventory_calls
        inventory_calls += 1
        raise OdooGatewayError("unavailable")

    factory = AgentRetrievalBindingFactory(
        sessions=unavailable_sessions,
        inventory_gateway_loader=inventory_loader,
        knowledge_backend_factory=lambda context: FakeKnowledgeBackend(),
    )
    executor = _executor(factory)

    result = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="knowledge-search",
                tool_name=KNOWLEDGE_SEARCH,
                arguments={"query": "payment terms"},
            )
        )
    )

    assert result.data["candidates"] == []
    assert executor.ledger.retrieved_evidence == ()
    assert inventory_calls == 0


def test_source_runtime_is_lazy_and_unavailable_error_is_sanitized() -> None:
    inventory_calls = 0

    def unavailable_sessions():
        raise AssertionError("source should fail before opening the Assistant DB")

    def inventory_loader():
        nonlocal inventory_calls
        inventory_calls += 1
        raise OdooGatewayError("network_detail_must_not_escape")

    factory = AgentRetrievalBindingFactory(
        sessions=unavailable_sessions,
        inventory_gateway_loader=inventory_loader,
        knowledge_backend_factory=lambda context: FakeKnowledgeBackend(),
    )
    executor = _executor(factory)

    with pytest.raises(ToolExecutorError, match="source_tool_unavailable"):
        asyncio.run(
            executor.execute(
                ToolCall(
                    call_id="source-find",
                    tool_name=SOURCE_FIND_SYMBOL,
                    arguments={"query": "action_confirm"},
                )
            )
        )

    assert inventory_calls == 1
