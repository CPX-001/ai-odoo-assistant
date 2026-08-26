"""Closed M7 maintenance contracts for explicit administrator operations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaintenanceOperation = Literal[
    "readiness_test",
    "source_rescan",
    "source_test",
    "logs_test",
    "knowledge_reindex",
    "reasoning_test",
    "configuration_revalidate",
]
MaintenanceJobOperation = Literal["source_rescan", "knowledge_reindex"]
MaintenanceState = Literal["queued", "running", "succeeded", "failed"]
MaintenanceResultCode = Literal[
    "readiness_ok",
    "readiness_degraded",
    "readiness_error",
    "readiness_test_failed",
    "source_rescan_succeeded",
    "source_rescan_failed",
    "source_test_succeeded",
    "source_test_failed",
    "logs_test_succeeded",
    "logs_test_failed",
    "knowledge_reindex_succeeded",
    "knowledge_reindex_incomplete",
    "knowledge_sources_unconfigured",
    "knowledge_source_limit",
    "knowledge_instance_unavailable",
    "knowledge_reindex_failed",
    "reasoning_operational",
    "reasoning_not_configured",
    "reasoning_runtime_missing",
    "reasoning_auth_unavailable",
    "reasoning_protocol_incompatible",
    "reasoning_error",
    "configuration_valid",
    "configuration_invalid",
    "configuration_unavailable",
    "maintenance_job_abandoned",
]


class MaintenanceActor(BaseModel):
    """Odoo-derived administrator identity used only for audit attribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    odoo_uid: int = Field(gt=0)
    odoo_database: str = Field(min_length=1, max_length=128, pattern=r"^[^\r\n\x00]+$")


class MaintenanceRequest(BaseModel):
    """Closed request shared by explicit maintenance endpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: MaintenanceActor


class MaintenanceMetrics(BaseModel):
    """Bounded counters only; no paths, excerpts, secrets or arbitrary metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_revision: int | None = Field(default=None, ge=0)
    source_modules: int | None = Field(default=None, ge=0, le=512)
    source_files_seen: int | None = Field(default=None, ge=0, le=5000)
    source_stale_files: int | None = Field(default=None, ge=0, le=5000)
    log_matches: int | None = Field(default=None, ge=0, le=20)
    knowledge_documents_seen: int | None = Field(default=None, ge=0, le=16384)
    knowledge_documents_indexed: int | None = Field(default=None, ge=0, le=16384)
    knowledge_documents_unchanged: int | None = Field(default=None, ge=0, le=16384)
    knowledge_documents_retired: int | None = Field(default=None, ge=0, le=16384)
    knowledge_errors: int | None = Field(default=None, ge=0, le=16384)
    knowledge_chunks: int | None = Field(default=None, ge=0, le=1_000_000)


class MaintenanceResult(BaseModel):
    """Sanitized result of one synchronous maintenance operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: MaintenanceOperation
    state: Literal["succeeded", "failed"]
    result_code: MaintenanceResultCode
    checked_at: datetime
    metrics: MaintenanceMetrics = Field(default_factory=MaintenanceMetrics)


class MaintenanceJob(BaseModel):
    """Minimal persisted state for maintenance work that may outlive a request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    operation: MaintenanceJobOperation
    state: MaintenanceState
    result_code: MaintenanceResultCode | None = None
    metrics: MaintenanceMetrics = Field(default_factory=MaintenanceMetrics)
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MaintenanceEvent(BaseModel):
    """Latest sanitized audit event suitable for the Odoo maintenance status panel."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: MaintenanceOperation
    state: MaintenanceState
    result_code: MaintenanceResultCode | None = None
    checked_at: datetime
    job_id: UUID | None = None
    metrics: MaintenanceMetrics = Field(default_factory=MaintenanceMetrics)


class MaintenanceStatus(BaseModel):
    """Bounded latest-result view; full audit browsing belongs to M7-06."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    latest: tuple[MaintenanceEvent, ...] = Field(default=(), max_length=7)
    active_jobs: tuple[MaintenanceJob, ...] = Field(default=(), max_length=2)
