"""Lazy knowledge/source bindings for the unified agent runtime."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Protocol, cast
from uuid import UUID

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
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolRegistry,
)

SessionFactory = Callable[[], Session]
InventoryGatewayLoader = Callable[[], OdooInstanceGateway]


def agent_retrieval_tool_specs() -> tuple[ToolSpec, ...]:
    """Reuse the existing bounded knowledge and structural-source catalogs."""

    return (*knowledge_tool_specs(), *source_tool_specs())


RETRIEVAL_TOOL_NAMES = frozenset(spec.name for spec in agent_retrieval_tool_specs())


class KnowledgeBackendFactory(Protocol):
    def __call__(self, context: ContextPack) -> KnowledgeToolBackend: ...


class SourceBackendFactory(Protocol):
    def __call__(self, context: ContextPack) -> SourceToolBackend: ...


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
        if any(spec.name not in knowledge_names | source_names for spec in specs):
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
        bindings = (
            *build_knowledge_tool_registry(knowledge_backend, knowledge_specs).bindings,
            *build_source_tool_registry(source_backend, source_specs).bindings,
        )
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
    """Resolve inventory/roots on the first source call; never scan in a normal turn."""

    def __init__(
        self,
        *,
        sessions: SessionFactory,
        inventory_gateway_loader: InventoryGatewayLoader,
    ) -> None:
        self._sessions = sessions
        self._inventory_gateway_loader = inventory_gateway_loader
        self._prepare_lock = asyncio.Lock()
        self._instance_profile_id: UUID | None = None
        self._roots: tuple[ResolvedSourceRoot, ...] | None = None

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
        async with self._prepare_lock:
            if self._instance_profile_id is not None and self._roots is not None:
                return self._instance_profile_id, self._roots
            try:
                gateway = self._inventory_gateway_loader()
                inventory = await gateway.get_instance_inventory()
                profile_id, roots = await asyncio.to_thread(
                    _prepare_source_runtime,
                    self._sessions,
                    inventory,
                )
            except ToolExecutorError:
                raise
            except (OdooGatewayError, SQLAlchemyError, OSError, RuntimeError, ValueError):
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
