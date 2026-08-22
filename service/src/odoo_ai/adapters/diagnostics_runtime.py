"""Runtime wiring for bounded M3 source and log diagnostics."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Literal, cast

from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.adapters.odoo_http import (
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
)
from odoo_ai.adapters.source_tools import (
    ensure_source_instance_profile,
    source_root_selection,
)
from odoo_ai.application import DiagnosticsError
from odoo_ai.contracts import (
    FindSymbolRequest,
    InstanceInventory,
    LogCapabilityState,
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    ReadExcerptRequest,
    SourceCapabilityState,
    SourceScanDiagnostics,
    SourceScanMetricsView,
    SourceStatusDiagnostics,
    SourceTestDiagnostics,
    TracebackRequest,
)
from odoo_ai.logs import (
    FileLogProvider,
    JournalLogProvider,
    JournalUnitSelection,
    LogFileSelection,
    LogProviderError,
    LogRedactor,
    journal_unit_override_from_env,
    log_file_override_from_env,
    resolve_journal_unit,
    resolve_log_file,
)
from odoo_ai.ports import LogProvider, OdooInstanceGateway
from odoo_ai.security import SharedSecretError, load_shared_secret
from odoo_ai.source import (
    SourceEvidenceService,
    SourceQueryError,
    SourceScanner,
    SqlAlchemySourceScanStore,
    m3_source_extractors,
    resolve_source_roots,
)
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    get_latest_capability_snapshot,
    get_latest_instance_profile,
    get_latest_scan_run,
    record_log_capability,
    session_scope,
)

InventoryGatewayLoader = Callable[[], OdooInstanceGateway]


class RuntimeDiagnosticsService:
    """Compose M3 adapters without exposing deployment details through HTTP."""

    def __init__(
        self,
        *,
        inventory_gateway_loader: InventoryGatewayLoader,
        database_settings: DatabaseSettings,
        log_provider: LogProvider | None,
        log_provider_name: str | None,
        unresolved_log_state: LogCapabilityState = LogCapabilityState.NOT_FOUND,
    ) -> None:
        self._inventory_gateway_loader = inventory_gateway_loader
        self._database_settings = database_settings
        self._log_provider = log_provider
        self._log_provider_name = log_provider_name
        self._unresolved_log_state = unresolved_log_state

    @classmethod
    def from_env(cls) -> RuntimeDiagnosticsService:
        settings = DatabaseSettings.from_env()

        def inventory_gateway() -> OdooInstanceGateway:
            return OdooGatewayFactory(OdooGatewaySettings.from_env()).for_instance()

        provider, provider_name, state = _log_provider_from_env()
        return cls(
            inventory_gateway_loader=inventory_gateway,
            database_settings=settings,
            log_provider=provider,
            log_provider_name=provider_name,
            unresolved_log_state=state,
        )

    async def source_status(self) -> SourceStatusDiagnostics:
        return await asyncio.to_thread(self._source_status_sync)

    async def rescan_source(self) -> SourceScanDiagnostics:
        inventory = await self._inventory()
        return await asyncio.to_thread(self._rescan_sync, inventory)

    async def test_source(self) -> SourceTestDiagnostics:
        inventory = await self._inventory()
        return await asyncio.to_thread(self._test_source_sync, inventory)

    async def test_logs(self, request: LogSearchRequest) -> LogTestDiagnostics:
        inventory = await self._inventory()
        if self._log_provider is None or self._log_provider_name is None:
            await asyncio.to_thread(
                self._record_log_state_sync, inventory, self._unresolved_log_state
            )
            raise DiagnosticsError("log_provider_unavailable", 409)
        try:
            results = await self._log_provider.search(request)
        except LogProviderError as error:
            await asyncio.to_thread(
                self._record_log_state_sync, inventory, _log_error_state(error.code)
            )
            raise DiagnosticsError(error.code, 409) from None
        await asyncio.to_thread(
            self._record_log_state_sync, inventory, LogCapabilityState.OPERATIONAL
        )
        return LogTestDiagnostics(
            provider=cast(Literal["file", "journal"], self._log_provider_name),
            results=tuple(results[:20]),
        )

    async def read_traceback(self, request: TracebackRequest) -> LogEvidence:
        if self._log_provider is None:
            raise DiagnosticsError("log_provider_unavailable", 409)
        try:
            result = await self._log_provider.read_traceback(
                request.fingerprint, max_bytes=request.max_bytes
            )
        except LogProviderError as error:
            status = 404 if error.code == "traceback_reference_unknown" else 422
            raise DiagnosticsError(error.code, status) from None
        if result is None:
            raise DiagnosticsError("traceback_reference_unknown", 404)
        return result

    async def _inventory(self) -> InstanceInventory:
        try:
            gateway = self._inventory_gateway_loader()
            return await gateway.get_instance_inventory()
        except (OdooGatewayError, OSError, ValueError):
            raise DiagnosticsError("instance_inventory_unavailable", 503) from None

    def _source_status_sync(self) -> SourceStatusDiagnostics:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            session_factory = create_session_factory(engine)
            with session_scope(session_factory) as session:
                profile = get_latest_instance_profile(session)
                if profile is None:
                    return SourceStatusDiagnostics(state="UNKNOWN", scan_status="unknown")
                snapshot = get_latest_capability_snapshot(session, instance_profile_id=profile.id)
                raw_state = snapshot.capabilities.get("source") if snapshot else None
                state: SourceCapabilityState | Literal["UNKNOWN"] = (
                    SourceCapabilityState(raw_state) if isinstance(raw_state, str) else "UNKNOWN"
                )
                scan = get_latest_scan_run(session, instance_profile_id=profile.id)
                if scan is None:
                    return SourceStatusDiagnostics(state=state, scan_status="unknown")
                return SourceStatusDiagnostics(
                    state=state,
                    scan_status=cast(Literal["running", "succeeded", "failed"], scan.status),
                    scan_id=scan.id,
                    fingerprint=scan.fingerprint,
                    completed_at=scan.completed_at,
                )
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise DiagnosticsError("source_status_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _rescan_sync(self, inventory: InstanceInventory) -> SourceScanDiagnostics:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            session_factory = create_session_factory(engine)
            with session_scope(session_factory) as session:
                profile = ensure_source_instance_profile(session, inventory)
                roots = source_root_selection(inventory)
                scanner = SourceScanner(
                    store=SqlAlchemySourceScanStore(session),
                    extractors=m3_source_extractors(),
                )
                result = scanner.run(
                    instance_profile_id=profile.id,
                    roots=roots,
                    installed_modules=inventory.installed_modules,
                )
                return SourceScanDiagnostics(
                    state=result.capability,
                    scan_id=result.scan_run_id,
                    fingerprint=result.fingerprint,
                    metrics=SourceScanMetricsView(
                        **{
                            name: getattr(result.metrics, name)
                            for name in SourceScanMetricsView.model_fields
                        }
                    ),
                    error_codes=tuple(dict.fromkeys(error.code for error in result.errors))[:32],
                )
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise DiagnosticsError("source_scan_failed", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _test_source_sync(self, inventory: InstanceInventory) -> SourceTestDiagnostics:
        engine = None
        try:
            roots = resolve_source_roots(source_root_selection(inventory)).roots
            if not roots:
                raise DiagnosticsError("source_roots_unavailable", 409)
            engine = create_database_engine(self._database_settings)
            session_factory = create_session_factory(engine)
            with session_scope(session_factory) as session:
                profile = ensure_source_instance_profile(session, inventory)
                service = SourceEvidenceService(session=session, roots=roots)
                result = service.find_symbol(
                    instance_profile_id=profile.id,
                    request=FindSymbolRequest(
                        query="action_confirm",
                        model="sale.order",
                        max_results=5,
                    ),
                )
                if not result.candidates:
                    raise DiagnosticsError("source_symbol_not_found", 404)
                candidate = result.candidates[0]
                excerpt = service.read_excerpt(
                    instance_profile_id=profile.id,
                    request=ReadExcerptRequest(
                        ref=candidate.ref,
                        context_before=2,
                        context_after=2,
                        max_lines=40,
                        max_bytes=16_384,
                    ),
                )
                return SourceTestDiagnostics(
                    candidate=candidate,
                    excerpt=excerpt,
                )
        except DiagnosticsError:
            raise
        except SourceQueryError as error:
            raise DiagnosticsError(error.code, 409) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise DiagnosticsError("source_test_failed", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _record_log_state_sync(
        self, inventory: InstanceInventory, state: LogCapabilityState
    ) -> None:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            session_factory = create_session_factory(engine)
            with session_scope(session_factory) as session:
                profile = ensure_source_instance_profile(session, inventory)
                record_log_capability(
                    session,
                    instance_profile_id=profile.id,
                    state=state,
                    provider=self._log_provider_name,
                )
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise DiagnosticsError("log_state_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()


def _log_provider_from_env() -> tuple[LogProvider | None, str | None, LogCapabilityState]:
    secrets: tuple[str, ...]
    try:
        secrets = (load_shared_secret(),)
    except SharedSecretError:
        secrets = ()
    redactor = LogRedactor(configured_secrets=secrets)
    file_resolution = resolve_log_file(LogFileSelection(override=log_file_override_from_env()))
    if file_resolution.resolved is not None:
        return (
            FileLogProvider(resolved=file_resolution.resolved, redactor=redactor),
            "file",
            LogCapabilityState.OPERATIONAL,
        )
    try:
        journal = resolve_journal_unit(
            JournalUnitSelection(override=journal_unit_override_from_env(os.environ))
        )
    except LogProviderError:
        return None, None, LogCapabilityState.ERROR
    if journal is not None:
        return (
            JournalLogProvider(resolved=journal, redactor=redactor),
            "journal",
            LogCapabilityState.OPERATIONAL,
        )
    return None, None, file_resolution.state


def _log_error_state(code: str) -> LogCapabilityState:
    if code in {"log_not_found", "journal_not_found"}:
        return LogCapabilityState.NOT_FOUND
    if code in {"log_no_permission", "journal_no_permission"}:
        return LogCapabilityState.NO_PERMISSION
    return LogCapabilityState.ERROR
