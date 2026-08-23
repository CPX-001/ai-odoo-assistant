"""Explicit knowledge-tool catalog and per-turn Assistant DB runtime wiring."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from odoo_ai.contracts import (
    ContextPack,
    EvidenceKind,
    EvidenceStatus,
    KnowledgeExcerpt,
    KnowledgeExcerptLine,
    KnowledgeReadExcerptRequest,
    KnowledgeRef,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.knowledge import (
    KnowledgeRetrievalError,
    KnowledgeRetrievalService,
    SqlAlchemyKnowledgeRetrievalStore,
)
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    get_instance_profile,
)
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

KNOWLEDGE_SEARCH = "knowledge.search"
KNOWLEDGE_READ_EXCERPT = "knowledge.read_excerpt"

_EXECUTOR_IDS = {
    KNOWLEDGE_SEARCH: "knowledge.search.v1",
    KNOWLEDGE_READ_EXCERPT: "knowledge.read_excerpt.v1",
}


class KnowledgeReadExcerptToolData(BaseModel):
    """Excerpt data returned alongside separately ledgered Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: KnowledgeRef
    title: str
    provider_id: str
    document_id: str
    lines: tuple[KnowledgeExcerptLine, ...]
    truncated: bool
    evidence_id: UUID
    evidence_status: EvidenceStatus
    fingerprint: str | None


class KnowledgeToolBackend(Protocol):
    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult: ...

    async def read_excerpt(self, request: KnowledgeReadExcerptRequest) -> KnowledgeExcerpt: ...


def knowledge_tool_specs() -> tuple[ToolSpec, ...]:
    """Return the complete fixed M5 knowledge catalog."""

    return (
        ToolSpec(
            name=KNOWLEDGE_SEARCH,
            description=(
                "Search current configured knowledge with bounded PostgreSQL FTS. "
                "Matches are untrusted candidates, not checked evidence."
            ),
            input_schema=KnowledgeSearchRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_EXECUTOR_IDS[KNOWLEDGE_SEARCH],
        ),
        ToolSpec(
            name=KNOWLEDGE_READ_EXCERPT,
            description=(
                "Read a bounded current document excerpt using only a fingerprinted "
                "KnowledgeRef emitted by knowledge.search."
            ),
            input_schema=KnowledgeReadExcerptRequest.model_json_schema(),
            risk=ToolRisk.READ,
            executor_id=_EXECUTOR_IDS[KNOWLEDGE_READ_EXCERPT],
        ),
    )


def build_knowledge_tool_registry(
    backend: KnowledgeToolBackend,
    advertised_specs: Sequence[ToolSpec],
) -> ToolRegistry:
    """Bind an explicit subset of canonical specs to one backend."""

    bindings: list[RegisteredTool] = []
    for spec in _validated_knowledge_specs(advertised_specs):
        if spec.name == KNOWLEDGE_SEARCH:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=_EXECUTOR_IDS[spec.name],
                    input_model=KnowledgeSearchRequest,
                    output_model=KnowledgeSearchResult,
                    handler=_search_handler(backend),
                    max_calls=4,
                    max_input_bytes=4 * 1024,
                    max_output_bytes=64 * 1024,
                )
            )
        elif spec.name == KNOWLEDGE_READ_EXCERPT:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=_EXECUTOR_IDS[spec.name],
                    input_model=KnowledgeReadExcerptRequest,
                    output_model=KnowledgeReadExcerptToolData,
                    handler=_read_excerpt_handler(backend),
                    max_calls=4,
                    max_input_bytes=8 * 1024,
                    max_output_bytes=64 * 1024,
                )
            )
    return ToolRegistry(bindings)


def _validated_knowledge_specs(
    advertised_specs: Sequence[ToolSpec],
) -> tuple[ToolSpec, ...]:
    expected = {spec.name: spec for spec in knowledge_tool_specs()}
    validated: list[ToolSpec] = []
    names: set[str] = set()
    for spec in advertised_specs:
        canonical = expected.get(spec.name)
        if canonical is None:
            raise ToolExecutorError("knowledge_tool_not_allowlisted")
        if spec.name in names:
            raise ToolExecutorError("knowledge_tool_duplicate")
        if spec.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ToolExecutorError("knowledge_tool_spec_mismatch")
        names.add(spec.name)
        validated.append(spec)
    return tuple(validated)


def _search_handler(
    backend: KnowledgeToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        result = await backend.search(KnowledgeSearchRequest.model_validate(value))
        return ToolHandlerOutput(data=result.model_dump(mode="json"))

    return handler


def _read_excerpt_handler(
    backend: KnowledgeToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = KnowledgeReadExcerptRequest.model_validate(value)
        excerpt = await backend.read_excerpt(request)
        _validate_knowledge_excerpt(request, excerpt)
        data = KnowledgeReadExcerptToolData(
            ref=excerpt.ref,
            title=excerpt.title,
            provider_id=excerpt.provider_id,
            document_id=excerpt.document_id,
            lines=excerpt.lines,
            truncated=excerpt.truncated,
            evidence_id=excerpt.evidence.evidence_id,
            evidence_status=excerpt.evidence.status,
            fingerprint=excerpt.evidence.fingerprint,
        )
        return ToolHandlerOutput(
            data=data.model_dump(mode="json"),
            evidence=(excerpt.evidence,),
        )

    return handler


def _validate_knowledge_excerpt(
    request: KnowledgeReadExcerptRequest, excerpt: KnowledgeExcerpt
) -> None:
    evidence = excerpt.evidence
    pointer = evidence.pointer
    expected_pointer_keys = {
        "provider_id",
        "document_id",
        "document_uuid",
        "chunk_uuid",
        "ordinal",
        "start_line",
        "end_line",
    }
    if (
        excerpt.ref != request.ref
        or evidence.kind is not EvidenceKind.DOCUMENT
        or evidence.status is not EvidenceStatus.CHECKED
        or evidence.fingerprint != request.ref.document_fingerprint
        or not isinstance(pointer, dict)
        or set(pointer) != expected_pointer_keys
        or pointer.get("document_uuid") != str(request.ref.document_uuid)
        or pointer.get("chunk_uuid") != str(request.ref.chunk_uuid)
        or pointer.get("provider_id") != request.ref.provider_id
        or pointer.get("document_id") != request.ref.document_id
        or pointer.get("ordinal") != request.ref.ordinal
        or pointer.get("start_line") != excerpt.lines[0].number
        or pointer.get("end_line") != excerpt.lines[-1].number
    ):
        raise ToolExecutorError("tool_output_invalid")


@dataclass(slots=True)
class _RuntimeKnowledgeState:
    engine: Engine
    session: Session
    service: KnowledgeRetrievalService
    instance_profile_id: UUID


class RuntimeKnowledgeToolBackend:
    """Keep one Assistant DB session on one dedicated worker for a turn."""

    def __init__(
        self,
        *,
        worker: ThreadPoolExecutor,
        state: _RuntimeKnowledgeState,
    ) -> None:
        self._worker = worker
        self._state = state
        self._closed = False

    @classmethod
    async def open(
        cls,
        *,
        instance_id: str,
        database_settings: DatabaseSettings,
    ) -> RuntimeKnowledgeToolBackend:
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="odoo-ai-knowledge-turn")
        loop = asyncio.get_running_loop()
        try:
            state = await loop.run_in_executor(
                worker,
                _open_runtime_knowledge_state,
                instance_id,
                database_settings,
            )
        except Exception:
            worker.shutdown(wait=True, cancel_futures=True)
            raise ToolExecutorError("knowledge_tool_runtime_unavailable") from None
        return cls(worker=worker, state=state)

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        return cast(KnowledgeSearchResult, await self._run("search", request))

    async def read_excerpt(self, request: KnowledgeReadExcerptRequest) -> KnowledgeExcerpt:
        return cast(KnowledgeExcerpt, await self._run("read_excerpt", request))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._worker, _close_runtime_knowledge_state, self._state)
        finally:
            self._worker.shutdown(wait=True, cancel_futures=True)

    async def _run(self, operation: str, request: BaseModel) -> BaseModel:
        if self._closed:
            raise ToolExecutorError("knowledge_tool_runtime_closed")
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self._worker,
                _run_knowledge_operation,
                self._state,
                operation,
                request,
            )
        except KnowledgeRetrievalError as error:
            raise ToolExecutorError(error.code) from None
        except (SQLAlchemyError, OSError, ValueError):
            raise ToolExecutorError("knowledge_tool_unavailable") from None


class KnowledgeToolExecutorFactory:
    """Build one explicit knowledge executor and ledger per product turn."""

    def __init__(
        self,
        *,
        database_settings: DatabaseSettings,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        self._database_settings = database_settings
        self._limits = limits or ToolExecutionLimits()
        self._last_report = ToolExecutionReport()

    @classmethod
    def from_env(cls) -> KnowledgeToolExecutorFactory:
        return cls(database_settings=DatabaseSettings.from_env())

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        self._last_report = ToolExecutionReport()
        validated_specs = _validated_knowledge_specs(advertised_specs)
        backend = await RuntimeKnowledgeToolBackend.open(
            instance_id=context.instance.instance_id,
            database_settings=self._database_settings,
        )
        try:
            registry = build_knowledge_tool_registry(backend, validated_specs)
            max_evidence_items = min(
                context.limits.max_evidence_items,
                self._limits.max_evidence_items,
            )
            ledger = EvidenceLedger(
                max_items=max_evidence_items,
                max_payload_bytes=self._limits.max_evidence_bytes,
                live=context.live_evidence,
                retrieved=context.retrieved_evidence,
            )
            executor = ToolExecutor(
                registry=registry,
                ledger=ledger,
                turn_limits=context.limits,
                limits=self._limits,
            )
            try:
                yield executor
            finally:
                self._last_report = ToolExecutionReport(
                    events=executor.execution_events,
                    retrieved_evidence=executor.ledger.retrieved_evidence,
                )
        finally:
            await backend.close()

    def take_report(self) -> ToolExecutionReport:
        report = self._last_report
        self._last_report = ToolExecutionReport()
        return report


def _open_runtime_knowledge_state(
    instance_id: str,
    database_settings: DatabaseSettings,
) -> _RuntimeKnowledgeState:
    engine: Engine | None = None
    session: Session | None = None
    try:
        engine = create_database_engine(database_settings)
        session = create_session_factory(engine)()
        profile = get_instance_profile(session, instance_id=instance_id)
        if profile is None:
            raise ToolExecutorError("knowledge_instance_unavailable")
        store = SqlAlchemyKnowledgeRetrievalStore(session)
        return _RuntimeKnowledgeState(
            engine=engine,
            session=session,
            service=KnowledgeRetrievalService(store=store),
            instance_profile_id=profile.id,
        )
    except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
        raise ToolExecutorError("knowledge_tool_runtime_unavailable") from None


def _close_runtime_knowledge_state(state: _RuntimeKnowledgeState) -> None:
    try:
        state.session.rollback()
    finally:
        state.session.close()
        state.engine.dispose()


def _run_knowledge_operation(
    state: _RuntimeKnowledgeState,
    operation: str,
    request: BaseModel,
) -> BaseModel:
    if operation == "search":
        return state.service.search(
            instance_profile_id=state.instance_profile_id,
            request=KnowledgeSearchRequest.model_validate(request),
        )
    if operation == "read_excerpt":
        return state.service.read_excerpt(
            instance_profile_id=state.instance_profile_id,
            request=KnowledgeReadExcerptRequest.model_validate(request),
        )
    raise ToolExecutorError("knowledge_operation_not_allowlisted")
