"""Runtime implementation of the explicit M7 maintenance catalog."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.adapters import CachedCodexReasoningStatus, RuntimeDiagnosticsService
from odoo_ai.application import DiagnosticsService
from odoo_ai.contracts.logs import LogSearchRequest
from odoo_ai.contracts.maintenance import (
    MaintenanceActor,
    MaintenanceEvent,
    MaintenanceJob,
    MaintenanceJobOperation,
    MaintenanceMetrics,
    MaintenanceOperation,
    MaintenanceResult,
    MaintenanceResultCode,
    MaintenanceState,
    MaintenanceStatus,
)
from odoo_ai.knowledge import (
    FilesystemKnowledgeLimits,
    FilesystemKnowledgeProvider,
    KnowledgeIngestionService,
    SqlAlchemyKnowledgeIngestStore,
    knowledge_sources_from_env,
)
from odoo_ai.runtime.admin_diagnostics import RuntimeAdminDiagnosticsService
from odoo_ai.runtime.configuration import RuntimeConfigurationError, RuntimeConfigurationService
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    get_latest_instance_profile,
    session_scope,
)
from odoo_ai.storage.maintenance_repository import (
    MaintenanceEventRecord,
    MaintenanceJobRecord,
    MaintenanceStoreError,
    create_maintenance_job,
    finish_maintenance_job,
    get_maintenance_job,
    list_active_maintenance_jobs,
    list_latest_maintenance_events,
    mark_maintenance_job_running,
    record_maintenance_event,
)

DiagnosticsFactory = Callable[[], DiagnosticsService]
AdminDiagnosticsFactory = Callable[[], RuntimeAdminDiagnosticsService]
ReasoningFactory = Callable[[], CachedCodexReasoningStatus]

MAX_MAINTENANCE_KNOWLEDGE_SOURCES = 16
MAINTENANCE_KNOWLEDGE_LIMITS = FilesystemKnowledgeLimits(max_seconds=10.0)


class RuntimeMaintenanceError(RuntimeError):
    """Sanitized maintenance-boundary failure safe for the admin API."""

    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class _KnowledgeFailure(RuntimeError):
    def __init__(self, code: MaintenanceResultCode) -> None:
        super().__init__(code)
        self.code = code


class RuntimeMaintenanceService:
    """Execute only the fixed maintenance operations and audit every attempt."""

    def __init__(
        self,
        *,
        database_settings: DatabaseSettings,
        environ: Mapping[str, str] | None = None,
        diagnostics_factory: DiagnosticsFactory = RuntimeDiagnosticsService.from_env,
        admin_diagnostics_factory: AdminDiagnosticsFactory = RuntimeAdminDiagnosticsService.from_env,
        reasoning_factory: ReasoningFactory = CachedCodexReasoningStatus.from_env,
    ) -> None:
        self._database_settings = database_settings
        self._environ = os.environ if environ is None else environ
        self._diagnostics_factory = diagnostics_factory
        self._admin_diagnostics_factory = admin_diagnostics_factory
        self._reasoning_factory = reasoning_factory

    @classmethod
    def from_env(cls) -> "RuntimeMaintenanceService":
        return cls(database_settings=DatabaseSettings.from_env())

    async def readiness_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        try:
            matrix = await self._admin_diagnostics_factory().inspect()
            code = cast(
                MaintenanceResultCode,
                {
                    "FULLY_READY": "readiness_ok",
                    "DEGRADED": "readiness_degraded",
                    "ERROR": "readiness_error",
                }[matrix.readiness],
            )
            metrics = MaintenanceMetrics(config_revision=matrix.config_revision)
            succeeded = True
        except Exception:  # noqa: BLE001 - fixed code only; no exception text escapes
            code = "readiness_test_failed"
            metrics = MaintenanceMetrics()
            succeeded = False
        return await self._direct_result(
            actor=actor,
            operation="readiness_test",
            succeeded=succeeded,
            result_code=code,
            metrics=metrics,
        )

    async def source_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        try:
            await self._diagnostics_factory().test_source()
            code: MaintenanceResultCode = "source_test_succeeded"
            succeeded = True
        except Exception:  # noqa: BLE001 - fixed result code only
            code = "source_test_failed"
            succeeded = False
        return await self._direct_result(
            actor=actor,
            operation="source_test",
            succeeded=succeeded,
            result_code=code,
        )

    async def logs_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        now = datetime.now(UTC)
        request = LogSearchRequest(
            from_ts=now - timedelta(hours=24),
            to_ts=now,
            terms=["Traceback"],
            max_lines=50,
            max_bytes=16_384,
        )
        try:
            result = await self._diagnostics_factory().test_logs(request)
            code: MaintenanceResultCode = "logs_test_succeeded"
            metrics = MaintenanceMetrics(log_matches=len(result.results))
            succeeded = True
        except Exception:  # noqa: BLE001 - provider internals remain private
            code = "logs_test_failed"
            metrics = MaintenanceMetrics()
            succeeded = False
        return await self._direct_result(
            actor=actor,
            operation="logs_test",
            succeeded=succeeded,
            result_code=code,
            metrics=metrics,
        )

    async def reasoning_test(self, actor: MaintenanceActor) -> MaintenanceResult:
        try:
            status = await self._reasoning_factory().inspect()
            code = cast(
                MaintenanceResultCode,
                {
                    "operational": "reasoning_operational",
                    "not_configured": "reasoning_not_configured",
                    "runtime_missing": "reasoning_runtime_missing",
                    "auth_unavailable": "reasoning_auth_unavailable",
                    "protocol_incompatible": "reasoning_protocol_incompatible",
                    "error": "reasoning_error",
                    "unknown": "reasoning_error",
                }.get(status.detail, "reasoning_error"),
            )
            succeeded = True
        except Exception:  # noqa: BLE001 - probe internals remain host-side
            code = "reasoning_error"
            succeeded = False
        return await self._direct_result(
            actor=actor,
            operation="reasoning_test",
            succeeded=succeeded,
            result_code=code,
        )

    async def configuration_revalidate(self, actor: MaintenanceActor) -> MaintenanceResult:
        try:
            response = await asyncio.to_thread(
                RuntimeConfigurationService(
                    database_settings=self._database_settings,
                    environ=self._environ,
                ).snapshot
            )
            code: MaintenanceResultCode = (
                "configuration_valid"
                if response.validation_state == "valid"
                else "configuration_invalid"
            )
            metrics = MaintenanceMetrics(config_revision=response.revision)
            succeeded = True
        except (RuntimeConfigurationError, DatabaseConfigurationError, OSError, ValueError):
            code = "configuration_unavailable"
            metrics = MaintenanceMetrics()
            succeeded = False
        return await self._direct_result(
            actor=actor,
            operation="configuration_revalidate",
            succeeded=succeeded,
            result_code=code,
            metrics=metrics,
        )

    async def enqueue_source_rescan(self, actor: MaintenanceActor) -> MaintenanceJob:
        return await asyncio.to_thread(self._create_job_sync, "source_rescan", actor)

    async def enqueue_knowledge_reindex(self, actor: MaintenanceActor) -> MaintenanceJob:
        return await asyncio.to_thread(self._create_job_sync, "knowledge_reindex", actor)

    async def run_source_rescan_job(self, job_id: UUID) -> None:
        try:
            await asyncio.to_thread(self._mark_job_running_sync, job_id)
        except RuntimeMaintenanceError:
            return
        try:
            result = await self._diagnostics_factory().rescan_source()
            metrics = MaintenanceMetrics(
                source_modules=result.metrics.modules,
                source_files_seen=result.metrics.files_seen,
                source_stale_files=result.metrics.stale_files,
            )
            await asyncio.to_thread(
                self._finish_job_sync,
                job_id,
                True,
                "source_rescan_succeeded",
                metrics,
            )
        except Exception:  # noqa: BLE001 - fixed background failure code only
            try:
                await asyncio.to_thread(
                    self._finish_job_sync,
                    job_id,
                    False,
                    "source_rescan_failed",
                    MaintenanceMetrics(),
                )
            except RuntimeMaintenanceError:
                return

    async def run_knowledge_reindex_job(self, job_id: UUID) -> None:
        try:
            await asyncio.to_thread(self._run_knowledge_reindex_sync, job_id)
        except RuntimeMaintenanceError:
            return

    async def job(self, job_id: UUID) -> MaintenanceJob:
        return await asyncio.to_thread(self._job_sync, job_id)

    async def status(self) -> MaintenanceStatus:
        return await asyncio.to_thread(self._status_sync)

    async def _direct_result(
        self,
        *,
        actor: MaintenanceActor,
        operation: MaintenanceOperation,
        succeeded: bool,
        result_code: MaintenanceResultCode,
        metrics: MaintenanceMetrics | None = None,
    ) -> MaintenanceResult:
        effective_metrics = metrics or MaintenanceMetrics()
        await asyncio.to_thread(
            self._record_direct_sync,
            actor,
            operation,
            succeeded,
            result_code,
            effective_metrics,
        )
        return MaintenanceResult(
            operation=operation,
            state="succeeded" if succeeded else "failed",
            result_code=result_code,
            checked_at=datetime.now(UTC),
            metrics=effective_metrics,
        )

    def _create_job_sync(
        self,
        operation: MaintenanceJobOperation,
        actor: MaintenanceActor,
    ) -> MaintenanceJob:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return _job_model(
                    create_maintenance_job(
                        session,
                        operation=operation,
                        actor_uid=actor.odoo_uid,
                        actor_database=actor.odoo_database,
                    )
                )
        except MaintenanceStoreError as error:
            status = 409 if error.code == "maintenance_job_active" else 503
            raise RuntimeMaintenanceError(error.code, status) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _mark_job_running_sync(self, job_id: UUID) -> MaintenanceJobRecord:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return mark_maintenance_job_running(session, job_id=job_id)
        except (
            MaintenanceStoreError,
            DatabaseConfigurationError,
            SQLAlchemyError,
            OSError,
            ValueError,
        ):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _finish_job_sync(
        self,
        job_id: UUID,
        succeeded: bool,
        result_code: MaintenanceResultCode,
        metrics: MaintenanceMetrics,
    ) -> MaintenanceJobRecord:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return finish_maintenance_job(
                    session,
                    job_id=job_id,
                    succeeded=succeeded,
                    result_code=result_code,
                    metrics=metrics,
                )
        except (
            MaintenanceStoreError,
            DatabaseConfigurationError,
            SQLAlchemyError,
            OSError,
            ValueError,
        ):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _run_knowledge_reindex_sync(self, job_id: UUID) -> None:
        self._mark_job_running_sync(job_id)
        result_code: MaintenanceResultCode = "knowledge_reindex_failed"
        metrics = MaintenanceMetrics()
        succeeded = False
        engine = None
        try:
            sources = knowledge_sources_from_env(self._environ)
            if not sources:
                raise _KnowledgeFailure("knowledge_sources_unconfigured")
            if len(sources) > MAX_MAINTENANCE_KNOWLEDGE_SOURCES:
                raise _KnowledgeFailure("knowledge_source_limit")

            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            totals: dict[str, int] = {
                "knowledge_documents_seen": 0,
                "knowledge_documents_indexed": 0,
                "knowledge_documents_unchanged": 0,
                "knowledge_documents_retired": 0,
                "knowledge_errors": 0,
                "knowledge_chunks": 0,
            }
            with session_scope(factory) as session:
                profile = get_latest_instance_profile(session)
                if profile is None:
                    raise _KnowledgeFailure("knowledge_instance_unavailable")
                ingestion = KnowledgeIngestionService(
                    store=SqlAlchemyKnowledgeIngestStore(session),
                    fts_config="simple",
                )
                for source in sources:
                    provider = FilesystemKnowledgeProvider(
                        source,
                        limits=MAINTENANCE_KNOWLEDGE_LIMITS,
                    )
                    result = ingestion.ingest(
                        instance_profile_id=profile.id,
                        provider=provider,
                    )
                    totals["knowledge_documents_seen"] += result.metrics.documents_seen
                    totals["knowledge_documents_indexed"] += result.metrics.documents_indexed
                    totals["knowledge_documents_unchanged"] += result.metrics.documents_unchanged
                    totals["knowledge_documents_retired"] += result.metrics.documents_retired
                    totals["knowledge_errors"] += result.metrics.errors
                    totals["knowledge_chunks"] += result.metrics.chunks
                    if not result.complete or result.metrics.errors:
                        raise _KnowledgeFailure("knowledge_reindex_incomplete")
            metrics = MaintenanceMetrics.model_validate(totals)
            result_code = "knowledge_reindex_succeeded"
            succeeded = True
        except _KnowledgeFailure as error:
            result_code = error.code
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            result_code = "knowledge_reindex_failed"
        finally:
            if engine is not None:
                engine.dispose()
        self._finish_job_sync(job_id, succeeded, result_code, metrics)

    def _record_direct_sync(
        self,
        actor: MaintenanceActor,
        operation: MaintenanceOperation,
        succeeded: bool,
        result_code: MaintenanceResultCode,
        metrics: MaintenanceMetrics,
    ) -> None:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                record_maintenance_event(
                    session,
                    operation=operation,
                    state="succeeded" if succeeded else "failed",
                    actor_uid=actor.odoo_uid,
                    actor_database=actor.odoo_database,
                    result_code=result_code,
                    metrics=metrics,
                )
        except (
            MaintenanceStoreError,
            DatabaseConfigurationError,
            SQLAlchemyError,
            OSError,
            ValueError,
        ):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _job_sync(self, job_id: UUID) -> MaintenanceJob:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return _job_model(get_maintenance_job(session, job_id=job_id))
        except MaintenanceStoreError as error:
            status = 404 if error.code == "maintenance_job_not_found" else 503
            raise RuntimeMaintenanceError(error.code, status) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _status_sync(self) -> MaintenanceStatus:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                latest = tuple(_event_model(row) for row in list_latest_maintenance_events(session))
                active = tuple(_job_model(row) for row in list_active_maintenance_jobs(session))
                return MaintenanceStatus(latest=latest, active_jobs=active)
        except (
            MaintenanceStoreError,
            DatabaseConfigurationError,
            SQLAlchemyError,
            OSError,
            ValueError,
        ):
            raise RuntimeMaintenanceError("maintenance_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()


def _job_model(record: MaintenanceJobRecord) -> MaintenanceJob:
    return MaintenanceJob(
        job_id=record.job_id,
        operation=cast(MaintenanceJobOperation, record.operation),
        state=cast(MaintenanceState, record.state),
        result_code=cast(MaintenanceResultCode | None, record.result_code),
        metrics=MaintenanceMetrics.model_validate(record.metrics),
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def _event_model(record: MaintenanceEventRecord) -> MaintenanceEvent:
    return MaintenanceEvent(
        operation=cast(MaintenanceOperation, record.operation),
        state=cast(MaintenanceState, record.state),
        result_code=cast(MaintenanceResultCode | None, record.result_code),
        checked_at=record.created_at,
        job_id=record.job_id,
        metrics=MaintenanceMetrics.model_validate(record.metrics),
    )
