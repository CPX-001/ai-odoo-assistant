import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from odoo_ai.adapters.agent_retrieval import (
    ODOO_GET_INSTANCE_FACTS,
    SOURCE_INSPECT_MODULE,
    AgentModuleInspectionRequest,
    AgentRetrievalBindingFactory,
    _inspect_module_operation,
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


class FakeSourceSession:
    def __init__(self, rows_by_call) -> None:
        self.rows_by_call = list(rows_by_call)
        self.rolled_back = False
        self.closed = False

    def scalar(self, statement):
        del statement
        return uuid4()

    def scalars(self, statement):
        del statement
        if not self.rows_by_call:
            raise AssertionError("unexpected additional source query")
        return self.rows_by_call.pop(0)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


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
    specs = {spec.name: spec for spec in agent_retrieval_tool_specs()}

    assert ODOO_GET_INSTANCE_FACTS in specs
    assert SOURCE_INSPECT_MODULE in specs
    inspect_properties = specs[SOURCE_INSPECT_MODULE].input_schema["properties"]
    assert "query" in inspect_properties
    assert inspect_properties["max_results"]["maximum"] == 24
    assert (
        specs[ODOO_GET_INSTANCE_FACTS].input_schema["properties"]["max_modules"]["maximum"]
        == 64
    )
    assert "XML records" in specs[SOURCE_INSPECT_MODULE].description
    assert "kind=xml_id" in specs[SOURCE_INSPECT_MODULE].description
    assert "odoo.get_instance_facts" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "source.inspect_module" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "Never invent an exact menu" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "res.config.settings" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "kind=xml_id" in _UNIFIED_AGENT_INSTRUCTIONS
    assert "exact visual location" in _UNIFIED_AGENT_INSTRUCTIONS


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


def test_instance_facts_maximum_contract_stays_inside_tool_output_budget() -> None:
    modules = tuple(
        f"module_{index:02d}_" + "x" * 238
        for index in range(64)
    )
    inventory = InstanceInventory(
        database="customer",
        server_version="18.0",
        installed_modules=modules,
        addons_roots=("/srv/odoo/addons",),
        captured_at=NOW,
    )
    gateway = FakeInventoryGateway(inventory)

    def sessions():
        raise AssertionError("instance facts must not open the Assistant database")

    executor = _executor(
        AgentRetrievalBindingFactory(
            sessions=sessions,
            inventory_gateway_loader=lambda: gateway,
            knowledge_backend_factory=lambda context: FakeKnowledgeBackend(),
        )
    )

    result = asyncio.run(
        executor.execute(
            ToolCall(
                call_id="instance-facts-max",
                tool_name=ODOO_GET_INSTANCE_FACTS,
                arguments={"max_modules": 64},
            )
        )
    )

    assert len(result.data["installed_modules"]) == 64
    assert result.data["modules_truncated"] is False
    assert gateway.calls == 1


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
                arguments={
                    "module": "custom_billing",
                    "query": "analytic",
                    "max_results": 20,
                },
            )
        )
    )

    assert result.data == {
        "module": "custom_billing",
        "installed": False,
        "indexed": False,
        "symbols": [],
        "truncated": False,
    }
    assert gateway.calls == 1


def test_indexed_module_inspection_returns_readable_source_refs() -> None:
    source_file_id = uuid4()
    fingerprint = "sha256:" + "a" * 64
    session = FakeSourceSession(
        (
            (
                SimpleNamespace(
                    source_file_id=source_file_id,
                    fingerprint=fingerprint,
                    start_line=20,
                    end_line=28,
                    kind="field",
                    model="res.config.settings",
                    name="analytic_accounting",
                    logical_path="custom_billing/models/res_config_settings.py",
                ),
            ),
            (),
        )
    )

    result = _inspect_module_operation(
        lambda: session,
        uuid4(),
        AgentModuleInspectionRequest(
            module="custom_billing",
            query="analytic",
            max_results=20,
        ),
    )

    assert result.installed is True
    assert result.indexed is True
    assert result.truncated is False
    assert len(result.symbols) == 1
    symbol = result.symbols[0]
    assert symbol.model == "res.config.settings"
    assert symbol.name == "analytic_accounting"
    assert symbol.ref.source_file_id == source_file_id
    assert symbol.ref.fingerprint == fingerprint
    assert symbol.ref.start_line == 20
    assert symbol.ref.end_line == 28
    assert session.rolled_back is True
    assert session.closed is True


def test_indexed_module_inspection_exposes_xml_view_refs() -> None:
    source_file_id = uuid4()
    fingerprint = "sha256:" + "b" * 64
    session = FakeSourceSession(
        (
            (),
            (
                SimpleNamespace(
                    source_file_id=source_file_id,
                    fingerprint=fingerprint,
                    start_line=8,
                    end_line=46,
                    model="ir.ui.view",
                    xml_id="custom_billing.res_config_settings_view_form",
                    logical_path="custom_billing/views/res_config_settings_views.xml",
                ),
            ),
        )
    )

    result = _inspect_module_operation(
        lambda: session,
        uuid4(),
        AgentModuleInspectionRequest(
            module="custom_billing",
            query="settings",
            max_results=20,
        ),
    )

    assert result.indexed is True
    assert result.truncated is False
    assert len(result.symbols) == 1
    xml = result.symbols[0]
    assert xml.kind == "xml_id"
    assert xml.model == "ir.ui.view"
    assert xml.name == "custom_billing.res_config_settings_view_form"
    assert xml.logical_path == "custom_billing/views/res_config_settings_views.xml"
    assert xml.ref.source_file_id == source_file_id
    assert xml.ref.fingerprint == fingerprint
    assert xml.ref.start_line == 8
    assert xml.ref.end_line == 46
    assert session.rolled_back is True
    assert session.closed is True


def test_module_inspection_truncation_keeps_python_and_xml_discoverable() -> None:
    fingerprint = "sha256:" + "c" * 64
    source_rows = tuple(
        SimpleNamespace(
            source_file_id=uuid4(),
            fingerprint=fingerprint,
            start_line=10 + index,
            end_line=11 + index,
            kind="field",
            model="res.config.settings",
            name=f"setting_{index}",
            logical_path="custom_billing/models/res_config_settings.py",
        )
        for index in range(3)
    )
    xml_rows = tuple(
        SimpleNamespace(
            source_file_id=uuid4(),
            fingerprint=fingerprint,
            start_line=30 + index,
            end_line=35 + index,
            model="ir.ui.view",
            xml_id=f"custom_billing.settings_view_{index}",
            logical_path="custom_billing/views/res_config_settings_views.xml",
        )
        for index in range(3)
    )
    session = FakeSourceSession((source_rows, xml_rows))

    result = _inspect_module_operation(
        lambda: session,
        uuid4(),
        AgentModuleInspectionRequest(
            module="custom_billing",
            query="settings",
            max_results=2,
        ),
    )

    assert result.truncated is True
    assert len(result.symbols) == 2
    assert result.symbols[0].kind == "field"
    assert result.symbols[1].kind == "xml_id"
