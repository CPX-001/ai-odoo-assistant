import asyncio
from datetime import UTC, datetime

from odoo_ai.adapters.agent_retrieval import (
    ODOO_GET_INSTANCE_FACTS,
    SOURCE_INSPECT_MODULE,
    AgentRetrievalBindingFactory,
    agent_retrieval_tool_specs,
)
from odoo_ai.adapters.knowledge_tools import KnowledgeToolBackend
from odoo_ai.adapters.unified_agent_engine import _UNIFIED_AGENT_INSTRUCTIONS
from odoo_ai.contracts import (
    ContextPack,
    ConversationState,
    EvidenceKind,
    EvidenceStatus,
    InstanceInventory,
    InstanceProfileSummary,
    KnowledgeSearchResult,
    ScreenContext,
    ToolRisk,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)
from odoo_ai.tools import (
    EvidenceLedger,
    ToolCall,
    ToolExecutionLimits,
    ToolExecutor,
    ToolRegistry,
)

NOW = datetime(2026, 8, 25, 11, 0, tzinfo=UTC)


class FakeKnowledgeBackend(KnowledgeToolBackend):
    async def search(self, request):
        return KnowledgeSearchResult(candidates=(), truncated=False)

    async def read_excerpt(self, request):
        raise AssertionError(f"unexpected knowledge read: {request}")


class FakeInventoryGateway:
    def __init__(self, inventory: InstanceInventory) -> None:
        self.inventory = inventory
        self.calls = 0

    async def get_instance_inventory(self) -> InstanceInventory:
        self.calls += 1
        return self.inventory


def _context() -> ContextPack:
    screen = ScreenContext(model="account.move", view_type="form", captured_at=NOW)
    return ContextPack(
        request=UserRequest(
            message="¿Hay alguna configuración que habilite opciones analíticas?"
        ),
        screen=screen,
        user=UserExecutionContext(uid=7, company_id=1, allowed_company_ids=[1]),
        workflow_hint=None,
        instance=InstanceProfileSummary(instance_id="odoo:customer"),
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=12, max_evidence_items=12),
    )


def _executor(factory: AgentRetrievalBindingFactory) -> ToolExecutor:
    context = _context()
    bindings = factory(context, agent_retrieval_tool_specs())
    return ToolExecutor(
        registry=ToolRegistry(
            bindings,
            allowed_risks={ToolRisk.READ, ToolRisk.METADATA},
        ),
        ledger=EvidenceLedger(max_items=12, max_payload_bytes=128 * 1024),
        turn_limits=context.limits,
        limits=ToolExecutionLimits(max_calls=12),
    )


def test_unified_agent_exposes_instance_and_module_discovery_tools() -> None:
    names = tuple(spec.name for spec in agent_retrieval_tool_specs())

    assert ODOO_GET_INSTANCE_FACTS in names
    assert SOURCE_INSPECT_MODULE in names
    assert "odoo.get_instance_facts" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "source.inspect_module" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "Never invent an exact menu" in _UNIFIED_AGENT_INSTRUCTIONS


def test_instance_facts_are_checked_cached_and_do_not_expose_host_paths() -> None:
    inventory = InstanceInventory(
        database="customer",
        server_version="18.0",
        installed_modules=("account", "analytic", "custom_billing"),
        addons_roots=("/srv/odoo/addons",),
        captured_at=NOW,
    )
    gateway = FakeInventoryGateway(inventory)

    def sessions():
        raise AssertionError("instance facts must not open the Assistant database")

    factory = AgentRetrievalBindingFactory(
        sessions=sessions,
        inventory_gateway_loader=lambda: gateway,
        knowledge_backend_factory=lambda context: FakeKnowledgeBackend(),
    )
    executor = _executor(factory)

    first = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="instance-facts-1",
                tool_name=ODOO_GET_INSTANCE_FACTS,
                arguments={"module_query": "analytic", "max_modules": 8},
            )
        )
    )
    second = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="instance-facts-2",
                tool_name=ODOO_GET_INSTANCE_FACTS,
                arguments={"module_query": "custom", "max_modules": 8},
            )
        )
    )

    assert first.data["server_version"] == "18.0"
    assert first.data["installed_modules"] == ["analytic"]
    assert second.data["installed_modules"] == ["custom_billing"]
    assert gateway.calls == 1

    evidence = executor.ledger.retrieved_evidence
    assert len(evidence) == 2
    assert all(item.kind is EvidenceKind.METADATA for item in evidence)
    assert all(item.status is EvidenceStatus.CHECKED for item in evidence)
    serialized = " ".join(item.model_dump_json() for item in evidence)
    assert "/srv/odoo/addons" not in serialized
    assert '"database":"customer"' not in serialized


def test_uninstalled_module_inspection_stops_before_source_database_access() -> None:
    inventory = InstanceInventory(
        database="customer",
        server_version="18.0",
        installed_modules=("account", "analytic"),
        addons_roots=("/srv/odoo/addons",),
        captured_at=NOW,
    )
    gateway = FakeInventoryGateway(inventory)

    def sessions():
        raise AssertionError("uninstalled module lookup must not open source persistence")

    factory = AgentRetrievalBindingFactory(
        sessions=sessions,
        inventory_gateway_loader=lambda: gateway,
        knowledge_backend_factory=lambda context: FakeKnowledgeBackend(),
    )
    executor = _executor(factory)

    result = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="inspect-missing",
                tool_name=SOURCE_INSPECT_MODULE,
                arguments={"module": "custom_billing", "max_results": 20},
            )
        )
    )

    assert result.data == {
        "module": "custom_billing",
        "installed": False,
        "symbols": [],
        "truncated": False,
    }
    assert gateway.calls == 1
