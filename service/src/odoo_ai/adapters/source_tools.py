"""Bounded source-tool catalog, handlers, and per-turn runtime wiring."""

from __future__ import annotations

import asyncio
import hashlib
import json
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

from odoo_ai.adapters.odoo_http import OdooGatewayFactory, OdooGatewaySettings
from odoo_ai.contracts import (
    ContextPack,
    EvidenceKind,
    EvidenceStatus,
    FindModelExtensionsRequest,
    FindModelExtensionsResult,
    FindSymbolRequest,
    FindSymbolResult,
    InstanceInventory,
    ReadExcerptRequest,
    SourceExcerpt,
    SourceExcerptLine,
    SourceFile,
    SourceRef,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.ports import OdooGatewayError, OdooInstanceGateway
from odoo_ai.source import (
    RootSelection,
    SourceEvidenceService,
    SourceQueryError,
    resolve_source_roots,
    source_root_overrides_from_env,
)
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    InstanceProfile,
    create_database_engine,
    create_instance_profile,
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

SOURCE_FIND_SYMBOL = "source.find_symbol"
SOURCE_FIND_MODEL_EXTENSIONS = "source.find_model_extensions"
SOURCE_READ_EXCERPT = "source.read_excerpt"

_EXECUTOR_IDS = {
    SOURCE_FIND_SYMBOL: "source.find_symbol.v1",
    SOURCE_FIND_MODEL_EXTENSIONS: "source.find_model_extensions.v1",
    SOURCE_READ_EXCERPT: "source.read_excerpt.v1",
}


class ReadExcerptToolData(BaseModel):
    """Excerpt data returned alongside separately ledgered Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: SourceRef
    module: str
    logical_path: str
    lines: tuple[SourceExcerptLine, ...]
    evidence_id: UUID
    evidence_status: EvidenceStatus
    fingerprint: str | None


class SourceToolBackend(Protocol):
    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult: ...

    async def find_model_extensions(
        self, request: FindModelExtensionsRequest
    ) -> FindModelExtensionsResult: ...

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt: ...


def source_tool_specs() -> tuple[ToolSpec, ...]:
    """Return the complete, fixed M4 source catalog from real Pydantic schemas."""

    return (
        ToolSpec(
            name=SOURCE_FIND_SYMBOL,
            description=(
                "Find bounded structural source symbols in the current index. "
                "Inputs never accept filesystem paths."
            ),
            input_schema=FindSymbolRequest.model_json_schema(),
            risk=ToolRisk.READ,
            executor_id=_EXECUTOR_IDS[SOURCE_FIND_SYMBOL],
        ),
        ToolSpec(
            name=SOURCE_FIND_MODEL_EXTENSIONS,
            description=(
                "Find indexed declarations related to one Odoo model without "
                "claiming runtime load order."
            ),
            input_schema=FindModelExtensionsRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_EXECUTOR_IDS[SOURCE_FIND_MODEL_EXTENSIONS],
        ),
        ToolSpec(
            name=SOURCE_READ_EXCERPT,
            description=(
                "Read a bounded fingerprint-checked excerpt using only a SourceRef "
                "previously emitted by the source index."
            ),
            input_schema=ReadExcerptRequest.model_json_schema(),
            risk=ToolRisk.READ,
            executor_id=_EXECUTOR_IDS[SOURCE_READ_EXCERPT],
        ),
    )


def build_source_tool_registry(
    backend: SourceToolBackend,
    advertised_specs: Sequence[ToolSpec],
) -> ToolRegistry:
    """Bind an explicit subset of the fixed catalog to one backend instance."""

    bindings: list[RegisteredTool] = []
    for spec in _validated_source_specs(advertised_specs):
        if spec.name == SOURCE_FIND_SYMBOL:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=_EXECUTOR_IDS[spec.name],
                    input_model=FindSymbolRequest,
                    output_model=FindSymbolResult,
                    handler=_find_symbol_handler(backend),
                    max_calls=4,
                    max_input_bytes=8 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == SOURCE_FIND_MODEL_EXTENSIONS:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=_EXECUTOR_IDS[spec.name],
                    input_model=FindModelExtensionsRequest,
                    output_model=FindModelExtensionsResult,
                    handler=_find_model_extensions_handler(backend),
                    max_calls=3,
                    max_input_bytes=8 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == SOURCE_READ_EXCERPT:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=_EXECUTOR_IDS[spec.name],
                    input_model=ReadExcerptRequest,
                    output_model=ReadExcerptToolData,
                    handler=_read_excerpt_handler(backend),
                    max_calls=4,
                    max_input_bytes=16 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
    return ToolRegistry(bindings)


def _validated_source_specs(advertised_specs: Sequence[ToolSpec]) -> tuple[ToolSpec, ...]:
    expected = {spec.name: spec for spec in source_tool_specs()}
    validated: list[ToolSpec] = []
    names: set[str] = set()
    for spec in advertised_specs:
        canonical = expected.get(spec.name)
        if canonical is None:
            raise ToolExecutorError("source_tool_not_allowlisted")
        if spec.name in names:
            raise ToolExecutorError("source_tool_duplicate")
        if spec.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ToolExecutorError("source_tool_spec_mismatch")
        names.add(spec.name)
        validated.append(spec)
    return tuple(validated)


def _find_symbol_handler(
    backend: SourceToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = FindSymbolRequest.model_validate(value)
        result = await backend.find_symbol(request)
        return ToolHandlerOutput(data=result.model_dump(mode="json"))

    return handler


def _find_model_extensions_handler(
    backend: SourceToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = FindModelExtensionsRequest.model_validate(value)
        result = await backend.find_model_extensions(request)
        for group in result.groups:
            _validate_logical_path(group.logical_path)
        return ToolHandlerOutput(data=result.model_dump(mode="json"))

    return handler


def _read_excerpt_handler(
    backend: SourceToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        request = ReadExcerptRequest.model_validate(value)
        excerpt = await backend.read_excerpt(request)
        _validate_source_excerpt(request, excerpt)
        data = ReadExcerptToolData(
            ref=excerpt.ref,
            module=excerpt.module,
            logical_path=excerpt.logical_path,
            lines=excerpt.lines,
            evidence_id=excerpt.evidence.evidence_id,
            evidence_status=excerpt.evidence.status,
            fingerprint=excerpt.evidence.fingerprint,
        )
        return ToolHandlerOutput(
            data=data.model_dump(mode="json"),
            evidence=(excerpt.evidence,),
        )

    return handler


def _validate_logical_path(value: str) -> None:
    try:
        SourceFile.validate_logical_path(value)
    except ValueError:
        raise ToolExecutorError("tool_output_invalid") from None


def _validate_source_excerpt(request: ReadExcerptRequest, excerpt: SourceExcerpt) -> None:
    _validate_logical_path(excerpt.logical_path)
    evidence = excerpt.evidence
    pointer = evidence.pointer
    if (
        excerpt.ref != request.ref
        or evidence.kind is not EvidenceKind.SOURCE
        or evidence.status is not EvidenceStatus.CHECKED
        or evidence.fingerprint != request.ref.fingerprint
        or not isinstance(pointer, dict)
        or set(pointer) != {"source_file_id", "logical_path", "start_line", "end_line"}
        or pointer.get("source_file_id") != str(request.ref.source_file_id)
        or pointer.get("logical_path") != excerpt.logical_path
    ):
        raise ToolExecutorError("tool_output_invalid")


def ensure_source_instance_profile(
    session: Session, inventory: InstanceInventory
) -> InstanceProfile:
    """Reuse the deterministic M3 instance identity for source runtime wiring."""

    instance_id = f"odoo:{inventory.database}"
    fingerprint = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "database": inventory.database,
                    "installed_modules": inventory.installed_modules,
                    "server_version": inventory.server_version,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    )
    profile = get_instance_profile(session, instance_id=instance_id)
    if profile is None:
        return create_instance_profile(session, instance_id=instance_id, fingerprint=fingerprint)
    profile.fingerprint = fingerprint
    session.flush()
    return profile


def source_root_selection(inventory: InstanceInventory) -> RootSelection:
    override = source_root_overrides_from_env()
    return RootSelection(
        override=override,
        runtime=() if override else inventory.addons_roots,
    )


@dataclass(slots=True)
class _RuntimeSourceState:
    engine: Engine
    session: Session
    service: SourceEvidenceService
    instance_profile_id: UUID


class RuntimeSourceToolBackend:
    """Keep one SQLAlchemy session on one dedicated worker for a product turn."""

    def __init__(
        self,
        *,
        worker: ThreadPoolExecutor,
        state: _RuntimeSourceState,
    ) -> None:
        self._worker = worker
        self._state = state
        self._closed = False

    @classmethod
    async def open(
        cls,
        *,
        inventory: InstanceInventory,
        database_settings: DatabaseSettings,
    ) -> RuntimeSourceToolBackend:
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="odoo-ai-source-turn")
        loop = asyncio.get_running_loop()
        try:
            state = await loop.run_in_executor(
                worker,
                _open_runtime_source_state,
                inventory,
                database_settings,
            )
        except Exception:
            worker.shutdown(wait=True, cancel_futures=True)
            raise ToolExecutorError("source_tool_runtime_unavailable") from None
        return cls(worker=worker, state=state)

    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult:
        return cast(
            FindSymbolResult,
            await self._run("find_symbol", request),
        )

    async def find_model_extensions(
        self, request: FindModelExtensionsRequest
    ) -> FindModelExtensionsResult:
        return cast(
            FindModelExtensionsResult,
            await self._run("find_model_extensions", request),
        )

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt:
        return cast(SourceExcerpt, await self._run("read_excerpt", request))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(self._worker, _close_runtime_source_state, self._state)
        finally:
            self._worker.shutdown(wait=True, cancel_futures=True)

    async def _run(self, operation: str, request: BaseModel) -> BaseModel:
        if self._closed:
            raise ToolExecutorError("source_tool_runtime_closed")
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self._worker,
                _run_source_operation,
                self._state,
                operation,
                request,
            )
        except SourceQueryError as error:
            raise ToolExecutorError(error.code) from None
        except (SQLAlchemyError, OSError, ValueError):
            raise ToolExecutorError("source_tool_unavailable") from None


class SourceToolExecutorFactory:
    """Build one source backend, registry, ledger, and executor per product turn."""

    def __init__(
        self,
        *,
        inventory_gateway_loader: Callable[[], OdooInstanceGateway],
        database_settings: DatabaseSettings,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        self._inventory_gateway_loader = inventory_gateway_loader
        self._database_settings = database_settings
        self._limits = limits or ToolExecutionLimits()
        self._last_report = ToolExecutionReport()

    @classmethod
    def from_env(cls) -> SourceToolExecutorFactory:
        def inventory_gateway() -> OdooInstanceGateway:
            return OdooGatewayFactory(OdooGatewaySettings.from_env()).for_instance()

        return cls(
            inventory_gateway_loader=inventory_gateway,
            database_settings=DatabaseSettings.from_env(),
        )

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        self._last_report = ToolExecutionReport()
        validated_specs = _validated_source_specs(advertised_specs)
        try:
            gateway = self._inventory_gateway_loader()
            inventory = await gateway.get_instance_inventory()
        except (OdooGatewayError, OSError, ValueError):
            raise ToolExecutorError("source_inventory_unavailable") from None
        backend = await RuntimeSourceToolBackend.open(
            inventory=inventory,
            database_settings=self._database_settings,
        )
        try:
            registry = build_source_tool_registry(backend, validated_specs)
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
        """Consume the report from this per-turn factory without retaining evidence."""

        report = self._last_report
        self._last_report = ToolExecutionReport()
        return report


def _open_runtime_source_state(
    inventory: InstanceInventory,
    database_settings: DatabaseSettings,
) -> _RuntimeSourceState:
    roots = resolve_source_roots(source_root_selection(inventory)).roots
    if not roots:
        raise ToolExecutorError("source_roots_unavailable")
    engine: Engine | None = None
    session: Session | None = None
    try:
        engine = create_database_engine(database_settings)
        session = create_session_factory(engine)()
        profile = ensure_source_instance_profile(session, inventory)
        session.commit()
        return _RuntimeSourceState(
            engine=engine,
            session=session,
            service=SourceEvidenceService(session=session, roots=roots),
            instance_profile_id=profile.id,
        )
    except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()
        raise ToolExecutorError("source_tool_runtime_unavailable") from None


def _close_runtime_source_state(state: _RuntimeSourceState) -> None:
    try:
        state.session.rollback()
    finally:
        state.session.close()
        state.engine.dispose()


def _run_source_operation(
    state: _RuntimeSourceState,
    operation: str,
    request: BaseModel,
) -> BaseModel:
    if operation == "find_symbol":
        return state.service.find_symbol(
            instance_profile_id=state.instance_profile_id,
            request=FindSymbolRequest.model_validate(request),
        )
    if operation == "find_model_extensions":
        return state.service.find_model_extensions(
            instance_profile_id=state.instance_profile_id,
            request=FindModelExtensionsRequest.model_validate(request),
        )
    if operation == "read_excerpt":
        return state.service.read_excerpt(
            instance_profile_id=state.instance_profile_id,
            request=ReadExcerptRequest.model_validate(request),
        )
    raise ToolExecutorError("source_operation_not_allowlisted")
