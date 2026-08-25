"""Lazy knowledge/source bindings for the unified agent runtime."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from odoo_ai.adapters.agent_timing import TimedToolExecutor
from odoo_ai.adapters.knowledge_tools import (
    KnowledgeToolBackend,
    build_knowledge_tool_registry,
    knowledge_tool_specs,
)
from odoo_ai.adapters.source_tools import (
    SourceToolBackend,
    build_source_tool_registry,
    ensure_source_instance_profile,
    source_root_selection,
    source_tool_specs,
)
from odoo_ai.contracts import (
    ActionToolReport,
    ContextPack,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    FindModelExtensionsRequest,
    FindModelExtensionsResult,
    FindSymbolRequest,
    FindSymbolResult,
    InstanceInventory,
    KnowledgeExcerpt,
    KnowledgeReadExcerptRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    ReadExcerptRequest,
    SourceExcerpt,
    SourceRef,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.knowledge import (
    KnowledgeRetrievalError,
    KnowledgeRetrievalService,
    SqlAlchemyKnowledgeRetrievalStore,
)
from odoo_ai.ports import OdooGatewayError, OdooInstanceGateway
from odoo_ai.source import (
    ResolvedSourceRoot,
    SourceEvidenceService,
    SourceQueryError,
    resolve_source_roots,
)
from odoo_ai.storage import get_instance_profile
from odoo_ai.storage.models import ScanRun, SourceFile, SourceSymbol, XmlRecord
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

SessionFactory = Callable[[], Session]
InventoryGatewayLoader = Callable[[], OdooInstanceGateway]

ODOO_GET_INSTANCE_FACTS = "odoo.get_instance_facts"
SOURCE_INSPECT_MODULE = "source.inspect_module"
_INSTANCE_FACTS_EXECUTOR_ID = "odoo.get_instance_facts.v1"
_INSPECT_MODULE_EXECUTOR_ID = "source.inspect_module.v1"
_MAX_INSTANCE_MODULES = 64
_MAX_MODULE_INSPECTION_RESULTS = 24


class AgentInstanceFactsRequest(BaseModel):
    """Bound the installed-module list returned to reasoning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_query: str | None = Field(default=None, min_length=1, max_length=128)
    max_modules: int = Field(default=64, strict=True, ge=1, le=_MAX_INSTANCE_MODULES)

    @field_validator("module_query")
    @classmethod
    def validate_module_query(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("module query must be normalized")
        return value


class AgentInstanceFactsData(BaseModel):
    """Sanitized runtime facts: no database name or physical addons roots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    server_version: str = Field(min_length=1, max_length=64)
    installed_modules: tuple[str, ...] = Field(max_length=_MAX_INSTANCE_MODULES)
    installed_module_count: int = Field(strict=True, ge=0, le=4096)
    matched_module_count: int = Field(strict=True, ge=0, le=4096)
    modules_truncated: bool
    captured_at: datetime


class AgentModuleInspectionRequest(BaseModel):
    """Inspect the indexed structure of one exact installed addon."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = Field(pattern=r"^[A-Za-z0-9_]+$", min_length=1, max_length=255)
    query: str | None = Field(default=None, min_length=1, max_length=128)
    max_results: int = Field(
        default=20,
        strict=True,
        ge=1,
        le=_MAX_MODULE_INSPECTION_RESULTS,
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("module inspection query must be normalized")
        return value


class AgentModuleSymbol(BaseModel):
    """One structural source pointer; content still requires source.read_excerpt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=512)
    logical_path: str = Field(min_length=1, max_length=1024)
    ref: SourceRef


class AgentModuleInspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = Field(pattern=r"^[A-Za-z0-9_]+$", min_length=1, max_length=255)
    installed: bool
    indexed: bool
    symbols: tuple[AgentModuleSymbol, ...] = Field(
        max_length=_MAX_MODULE_INSPECTION_RESULTS
    )
    truncated: bool


def agent_retrieval_tool_specs() -> tuple[ToolSpec, ...]:
    """Expose bounded instance facts, knowledge, and structural source discovery."""

    return (
        ToolSpec(
            name=ODOO_GET_INSTANCE_FACTS,
            description=(
                "Read the actual Odoo server version and installed addon technical names from "
                "the running instance. Use when an answer can differ by Odoo version or module "
                "installation. Physical addons paths are never returned."
            ),
            input_schema=AgentInstanceFactsRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_INSTANCE_FACTS_EXECUTOR_ID,
        ),
        *knowledge_tool_specs(),
        *source_tool_specs(),
        ToolSpec(
            name=SOURCE_INSPECT_MODULE,
            description=(
                "List bounded indexed Python structural symbols and XML records for one exact "
                "installed Odoo addon, optionally filtering names/models/kinds/logical paths by "
                "a short query. XML records are returned as kind=xml_id. Use when the relevant "
                "symbol or Settings/view implementation is not yet known, then call "
                "source.read_excerpt on only the useful returned refs."
            ),
            input_schema=AgentModuleInspectionRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_INSPECT_MODULE_EXECUTOR_ID,
        ),
    )


RETRIEVAL_TOOL_NAMES = frozenset(spec.name for spec in agent_retrieval_tool_specs())


class KnowledgeBackendFactory(Protocol):
    def __call__(self, context: ContextPack) -> KnowledgeToolBackend: ...


class AgentSourceBackend(SourceToolBackend, Protocol):
    async def get_instance_inventory(self) -> InstanceInventory: ...

    async def inspect_module(
        self,
        request: AgentModuleInspectionRequest,
    ) -> AgentModuleInspectionResult: ...


class SourceBackendFactory(Protocol):
    def __call__(self, context: ContextPack) -> AgentSourceBackend: ...


class AgentRetrievalBindingFactory:
    """Build retrieval handlers without allocating DB/source infrastructure per turn."""

    def __init__(
        self,
        *,
        sessions: SessionFactory,
        inventory_gateway_loader: InventoryGatewayLoader,
        knowledge_backend_factory: KnowledgeBackendFactory | None = None,
        source_backend_factory: SourceBackendFactory | None = None,
    ) -> None:
        self._sessions = sessions
        self._inventory_gateway_loader = inventory_gateway_loader
        self._knowledge_backend_factory = knowledge_backend_factory
        self._source_backend_factory = source_backend_factory

    def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> tuple[RegisteredTool, ...]:
        specs = tuple(advertised_specs)
        knowledge_names = {spec.name for spec in knowledge_tool_specs()}
        source_names = {spec.name for spec in source_tool_specs()}
        extra_names = {ODOO_GET_INSTANCE_FACTS, SOURCE_INSPECT_MODULE}
        allowed_names = knowledge_names | source_names | extra_names
        if any(spec.name not in allowed_names for spec in specs):
            raise ToolExecutorError("agent_retrieval_tool_not_allowlisted")

        knowledge_specs = tuple(spec for spec in specs if spec.name in knowledge_names)
        source_specs = tuple(spec for spec in specs if spec.name in source_names)
        knowledge_backend = (
            self._knowledge_backend_factory(context)
            if self._knowledge_backend_factory is not None
            else SharedSessionKnowledgeBackend(
                sessions=self._sessions,
                instance_id=context.instance.instance_id,
            )
        )
        source_backend = (
            self._source_backend_factory(context)
            if self._source_backend_factory is not None
            else LazySharedSessionSourceBackend(
                sessions=self._sessions,
                inventory_gateway_loader=self._inventory_gateway_loader,
            )
        )

        by_name: dict[str, RegisteredTool] = {}
        for binding in build_knowledge_tool_registry(
            knowledge_backend,
            knowledge_specs,
        ).bindings:
            by_name[binding.spec.name] = binding
        for binding in build_source_tool_registry(source_backend, source_specs).bindings:
            by_name[binding.spec.name] = binding
        for spec in specs:
            if spec.name == ODOO_GET_INSTANCE_FACTS:
                by_name[spec.name] = _instance_facts_binding(source_backend, spec)
            elif spec.name == SOURCE_INSPECT_MODULE:
                by_name[spec.name] = _inspect_module_binding(source_backend, spec)

        try:
            bindings = tuple(by_name[spec.name] for spec in specs)
        except KeyError:
            raise ToolExecutorError("agent_retrieval_registry_mismatch") from None
        if tuple(binding.spec for binding in bindings) != specs:
            raise ToolExecutorError("agent_retrieval_registry_mismatch")
        return bindings


class RetrievalOnlyToolExecutorFactory:
    """Allow source/knowledge questions even when no Odoo model candidate is needed."""

    def __init__(
        self,
        *,
        binding_factory: AgentRetrievalBindingFactory,
        limits: ToolExecutionLimits,
    ) -> None:
        self._binding_factory = binding_factory
        self._limits = limits
        self._last_report = ActionToolReport()

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        specs = tuple(advertised_specs)
        if not specs or any(spec.name not in RETRIEVAL_TOOL_NAMES for spec in specs):
            raise ToolExecutorError("agent_retrieval_registry_mismatch")
        bindings = self._binding_factory(context, specs)
        registry = ToolRegistry(
            bindings,
            allowed_risks={ToolRisk.READ, ToolRisk.METADATA},
        )
        ledger = EvidenceLedger(
            max_items=min(
                context.limits.max_evidence_items,
                self._limits.max_evidence_items,
            ),
            max_payload_bytes=self._limits.max_evidence_bytes,
            live=context.live_evidence,
            retrieved=context.retrieved_evidence,
        )
        executor = TimedToolExecutor(
            registry=registry,
            ledger=ledger,
            turn_limits=context.limits,
            limits=self._limits,
        )
        try:
            yield executor
        finally:
            self._last_report = ActionToolReport(
                tool_report=ToolExecutionReport(
                    events=executor.execution_events,
                    retrieved_evidence=executor.ledger.retrieved_evidence,
                )
            )

    def take_report(self) -> ActionToolReport:
        report = self._last_report
        self._last_report = ActionToolReport()
        return report


class SharedSessionKnowledgeBackend:
    """Use a fresh Session from the RuntimeAgentFactory shared engine per operation."""

    def __init__(self, *, sessions: SessionFactory, instance_id: str) -> None:
        self._sessions = sessions
        self._instance_id = instance_id

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        return cast(KnowledgeSearchResult, await self._run("search", request))

    async def read_excerpt(self, request: KnowledgeReadExcerptRequest) -> KnowledgeExcerpt:
        return cast(KnowledgeExcerpt, await self._run("read_excerpt", request))

    async def _run(self, operation: str, request: object) -> object:
        try:
            return await asyncio.to_thread(
                _run_knowledge_operation,
                self._sessions,
                self._instance_id,
                operation,
                request,
            )
        except KnowledgeRetrievalError as error:
            raise ToolExecutorError(error.code) from None
        except ToolExecutorError:
            raise
        except (SQLAlchemyError, OSError, RuntimeError, ValueError):
            raise ToolExecutorError("knowledge_tool_unavailable") from None


class LazySharedSessionSourceBackend:
    """Resolve inventory/roots lazily; never run the source scanner during a turn."""

    def __init__(
        self,
        *,
        sessions: SessionFactory,
        inventory_gateway_loader: InventoryGatewayLoader,
    ) -> None:
        self._sessions = sessions
        self._inventory_gateway_loader = inventory_gateway_loader
        self._inventory_lock = asyncio.Lock()
        self._prepare_lock = asyncio.Lock()
        self._inventory: InstanceInventory | None = None
        self._instance_profile_id: UUID | None = None
        self._roots: tuple[ResolvedSourceRoot, ...] | None = None

    async def get_instance_inventory(self) -> InstanceInventory:
        if self._inventory is not None:
            return self._inventory
        async with self._inventory_lock:
            if self._inventory is not None:
                return self._inventory
            try:
                gateway = self._inventory_gateway_loader()
                inventory = await gateway.get_instance_inventory()
            except ToolExecutorError:
                raise
            except (OdooGatewayError, OSError, RuntimeError, ValueError):
                raise ToolExecutorError("source_tool_unavailable") from None
            self._inventory = inventory
            return inventory

    async def inspect_module(
        self,
        request: AgentModuleInspectionRequest,
    ) -> AgentModuleInspectionResult:
        inventory = await self.get_instance_inventory()
        if request.module not in inventory.installed_modules:
            return AgentModuleInspectionResult(
                module=request.module,
                installed=False,
                indexed=False,
                symbols=(),
                truncated=False,
            )
        profile_id, _ = await self._prepare()
        try:
            return await asyncio.to_thread(
                _inspect_module_operation,
                self._sessions,
                profile_id,
                request,
            )
        except ToolExecutorError:
            raise
        except (SQLAlchemyError, OSError, RuntimeError, ValueError):
            raise ToolExecutorError("source_tool_unavailable") from None

    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult:
        return cast(FindSymbolResult, await self._run("find_symbol", request))

    async def find_model_extensions(
        self,
        request: FindModelExtensionsRequest,
    ) -> FindModelExtensionsResult:
        return cast(
            FindModelExtensionsResult,
            await self._run("find_model_extensions", request),
        )

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt:
        return cast(SourceExcerpt, await self._run("read_excerpt", request))

    async def _prepare(self) -> tuple[UUID, tuple[ResolvedSourceRoot, ...]]:
        if self._instance_profile_id is not None and self._roots is not None:
            return self._instance_profile_id, self._roots
        inventory = await self.get_instance_inventory()
        async with self._prepare_lock:
            if self._instance_profile_id is not None and self._roots is not None:
                return self._instance_profile_id, self._roots
            try:
                profile_id, roots = await asyncio.to_thread(
                    _prepare_source_runtime,
                    self._sessions,
                    inventory,
                )
            except ToolExecutorError:
                raise
            except (SQLAlchemyError, OSError, RuntimeError, ValueError):
                raise ToolExecutorError("source_tool_unavailable") from None
            self._instance_profile_id = profile_id
            self._roots = roots
            return profile_id, roots

    async def _run(self, operation: str, request: object) -> object:
        profile_id, roots = await self._prepare()
        try:
            return await asyncio.to_thread(
                _run_source_operation,
                self._sessions,
                profile_id,
                roots,
                operation,
                request,
            )
        except SourceQueryError as error:
            raise ToolExecutorError(error.code) from None
        except ToolExecutorError:
            raise
        except (SQLAlchemyError, OSError, RuntimeError, ValueError):
            raise ToolExecutorError("source_tool_unavailable") from None


def _instance_facts_binding(
    backend: AgentSourceBackend,
    spec: ToolSpec,
) -> RegisteredTool:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = AgentInstanceFactsRequest.model_validate(value)
        inventory = await backend.get_instance_inventory()
        modules = tuple(inventory.installed_modules)
        if request.module_query is not None:
            needle = request.module_query.casefold()
            matched = tuple(module for module in modules if needle in module.casefold())
        else:
            matched = modules
        selected = matched[: request.max_modules]
        data = AgentInstanceFactsData(
            server_version=inventory.server_version,
            installed_modules=selected,
            installed_module_count=len(modules),
            matched_module_count=len(matched),
            modules_truncated=len(matched) > len(selected),
            captured_at=inventory.captured_at,
        )
        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Odoo runtime facts",
            summary="Machine-authenticated Odoo version and installed-module metadata.",
            payload=data.model_dump(mode="json"),
            pointer={"subject": "instance_inventory"},
            observed_at=inventory.captured_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
        )
        return ToolHandlerOutput(
            data=data.model_dump(mode="json"),
            evidence=(evidence,),
        )

    return RegisteredTool(
        spec=spec,
        executor_id=_INSTANCE_FACTS_EXECUTOR_ID,
        input_model=AgentInstanceFactsRequest,
        output_model=AgentInstanceFactsData,
        handler=handler,
        max_calls=4,
        max_input_bytes=2 * 1024,
        max_output_bytes=64 * 1024,
    )


def _inspect_module_binding(
    backend: AgentSourceBackend,
    spec: ToolSpec,
) -> RegisteredTool:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = AgentModuleInspectionRequest.model_validate(value)
        result = await backend.inspect_module(request)
        return ToolHandlerOutput(data=result.model_dump(mode="json"))

    return RegisteredTool(
        spec=spec,
        executor_id=_INSPECT_MODULE_EXECUTOR_ID,
        input_model=AgentModuleInspectionRequest,
        output_model=AgentModuleInspectionResult,
        handler=handler,
        max_calls=4,
        max_input_bytes=2 * 1024,
        max_output_bytes=96 * 1024,
    )


def _run_knowledge_operation(
    sessions: SessionFactory,
    instance_id: str,
    operation: str,
    request: object,
) -> object:
    session = sessions()
    try:
        profile = get_instance_profile(session, instance_id=instance_id)
        if profile is None:
            raise ToolExecutorError("knowledge_tool_unavailable")
        service = KnowledgeRetrievalService(
            store=SqlAlchemyKnowledgeRetrievalStore(session)
        )
        if operation == "search":
            return service.search(
                instance_profile_id=profile.id,
                request=KnowledgeSearchRequest.model_validate(request),
            )
        if operation == "read_excerpt":
            return service.read_excerpt(
                instance_profile_id=profile.id,
                request=KnowledgeReadExcerptRequest.model_validate(request),
            )
        raise ToolExecutorError("knowledge_operation_not_allowlisted")
    finally:
        session.rollback()
        session.close()


def _prepare_source_runtime(
    sessions: SessionFactory,
    inventory: InstanceInventory,
) -> tuple[UUID, tuple[ResolvedSourceRoot, ...]]:
    roots = resolve_source_roots(source_root_selection(inventory)).roots
    if not roots:
        raise ToolExecutorError("source_tool_unavailable")
    session = sessions()
    try:
        profile = ensure_source_instance_profile(session, inventory)
        session.commit()
        return profile.id, roots
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _inspect_module_operation(
    sessions: SessionFactory,
    instance_profile_id: UUID,
    request: AgentModuleInspectionRequest,
) -> AgentModuleInspectionResult:
    session = sessions()
    try:
        indexed_file_id = session.scalar(
            select(SourceFile.id)
            .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
            .where(
                SourceFile.instance_profile_id == instance_profile_id,
                SourceFile.module == request.module,
                SourceFile.is_stale.is_(False),
                ScanRun.status == "succeeded",
            )
            .limit(1)
        )
        if indexed_file_id is None:
            return AgentModuleInspectionResult(
                module=request.module,
                installed=True,
                indexed=False,
                symbols=(),
                truncated=False,
            )

        symbol_statement = (
            select(SourceSymbol)
            .join(SourceFile, SourceFile.id == SourceSymbol.source_file_id)
            .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
            .where(
                SourceFile.instance_profile_id == instance_profile_id,
                SourceFile.module == request.module,
                SourceFile.is_stale.is_(False),
                SourceSymbol.fingerprint == SourceFile.fingerprint,
                ScanRun.status == "succeeded",
            )
        )
        xml_statement = (
            select(XmlRecord)
            .join(SourceFile, SourceFile.id == XmlRecord.source_file_id)
            .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
            .where(
                SourceFile.instance_profile_id == instance_profile_id,
                SourceFile.module == request.module,
                SourceFile.is_stale.is_(False),
                XmlRecord.fingerprint == SourceFile.fingerprint,
                XmlRecord.start_line.is_not(None),
                XmlRecord.end_line.is_not(None),
                ScanRun.status == "succeeded",
            )
        )
        if request.query is not None:
            normalized = request.query.casefold()
            symbol_statement = symbol_statement.where(
                or_(
                    func.lower(SourceSymbol.name).contains(normalized, autoescape=True),
                    func.lower(SourceSymbol.model).contains(normalized, autoescape=True),
                    func.lower(SourceSymbol.kind).contains(normalized, autoescape=True),
                    func.lower(SourceSymbol.logical_path).contains(
                        normalized, autoescape=True
                    ),
                )
            )
            xml_statement = xml_statement.where(
                or_(
                    func.lower(XmlRecord.xml_id).contains(normalized, autoescape=True),
                    func.lower(XmlRecord.model).contains(normalized, autoescape=True),
                    func.lower(XmlRecord.logical_path).contains(normalized, autoescape=True),
                )
            )

        source_rows = tuple(
            session.scalars(
                symbol_statement.order_by(
                    SourceSymbol.kind,
                    SourceSymbol.model,
                    SourceSymbol.name,
                    SourceSymbol.id,
                ).limit(request.max_results + 1)
            )
        )
        xml_rows = tuple(
            session.scalars(
                xml_statement.order_by(
                    XmlRecord.model,
                    XmlRecord.xml_id,
                    XmlRecord.id,
                ).limit(request.max_results + 1)
            )
        )
        source_entries = tuple(
            AgentModuleSymbol(
                kind=row.kind,
                model=row.model,
                name=row.name,
                logical_path=row.logical_path,
                ref=SourceRef(
                    source_file_id=row.source_file_id,
                    fingerprint=row.fingerprint,
                    start_line=row.start_line,
                    end_line=row.end_line,
                ),
            )
            for row in source_rows
        )
        xml_entries = tuple(
            AgentModuleSymbol(
                kind="xml_id",
                model=row.model,
                name=row.xml_id,
                logical_path=row.logical_path,
                ref=SourceRef(
                    source_file_id=row.source_file_id,
                    fingerprint=row.fingerprint,
                    start_line=cast(int, row.start_line),
                    end_line=cast(int, row.end_line),
                ),
            )
            for row in xml_rows
        )
        selected = _interleave_module_entries(
            source_entries,
            xml_entries,
            limit=request.max_results,
        )
        return AgentModuleInspectionResult(
            module=request.module,
            installed=True,
            indexed=True,
            symbols=selected,
            truncated=len(source_entries) + len(xml_entries) > len(selected),
        )
    finally:
        session.rollback()
        session.close()


def _interleave_module_entries(
    source_entries: tuple[AgentModuleSymbol, ...],
    xml_entries: tuple[AgentModuleSymbol, ...],
    *,
    limit: int,
) -> tuple[AgentModuleSymbol, ...]:
    """Keep both Python and XML discoverable inside one bounded result."""

    selected: list[AgentModuleSymbol] = []
    for index in range(max(len(source_entries), len(xml_entries))):
        if index < len(source_entries):
            selected.append(source_entries[index])
            if len(selected) >= limit:
                break
        if index < len(xml_entries):
            selected.append(xml_entries[index])
            if len(selected) >= limit:
                break
    return tuple(selected)


def _run_source_operation(
    sessions: SessionFactory,
    instance_profile_id: UUID,
    roots: tuple[ResolvedSourceRoot, ...],
    operation: str,
    request: object,
) -> object:
    session = sessions()
    try:
        service = SourceEvidenceService(session=session, roots=roots)
        if operation == "find_symbol":
            return service.find_symbol(
                instance_profile_id=instance_profile_id,
                request=FindSymbolRequest.model_validate(request),
            )
        if operation == "find_model_extensions":
            return service.find_model_extensions(
                instance_profile_id=instance_profile_id,
                request=FindModelExtensionsRequest.model_validate(request),
            )
        if operation == "read_excerpt":
            return service.read_excerpt(
                instance_profile_id=instance_profile_id,
                request=ReadExcerptRequest.model_validate(request),
            )
        raise ToolExecutorError("source_operation_not_allowlisted")
    finally:
        session.rollback()
        session.close()
