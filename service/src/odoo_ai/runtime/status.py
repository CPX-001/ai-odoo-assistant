"""Deterministic and sanitized runtime readiness inspection."""

import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    get_latest_instance_profile,
    record_reasoning_capability,
)


class ComponentState(StrEnum):
    OK = "ok"
    ERROR = "error"
    PENDING = "pending"


class ComponentStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: ComponentState
    detail: str


class MigrationStatus(ComponentStatus):
    current_revision: str | None = None
    expected_revision: str | None = None


class ReasoningComponentStatus(ComponentStatus):
    provider: Literal["codex"] = "codex"
    protocol: str | None = None
    runtime_version: str | None = None
    model: str | None = None


class InstanceStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    instance_id: str
    fingerprint: str
    reported_readiness: str | None = None
    capabilities: dict[str, JsonValue]


class RuntimeComponents(BaseModel):
    model_config = ConfigDict(frozen=True)

    runtime: ComponentStatus
    assistant_database: ComponentStatus
    migrations: MigrationStatus
    source: ComponentStatus
    logs: ComponentStatus
    reasoning_engine: ReasoningComponentStatus


class WorkflowCapabilities(BaseModel):
    """M5 workflow diagnostics that do not redefine global readiness."""

    model_config = ConfigDict(frozen=True)

    query: ComponentStatus
    navigation: ComponentStatus
    knowledge: ComponentStatus
    how_to: ComponentStatus


class AdminStatus(BaseModel):
    """Stable, sanitized readiness payload for Odoo Diagnostics."""

    model_config = ConfigDict(frozen=True)

    readiness: Literal["FULLY_READY", "DEGRADED", "ERROR"]
    checked_at: datetime
    components: RuntimeComponents
    workflow_capabilities: WorkflowCapabilities
    pending_capabilities: tuple[str, ...]
    instance: InstanceStatus | None = None


class AdminStatusService:
    """Inspect process, Assistant DB, migration revision, and stored runtime facts."""

    _PENDING_CAPABILITIES = ("source", "logs", "reasoning_engine")

    def __init__(self, *, settings: DatabaseSettings, alembic_config_path: Path) -> None:
        self._settings = settings
        self._alembic_config_path = alembic_config_path

    @classmethod
    def from_env(cls) -> "AdminStatusService":
        default_alembic_config = str(Path(__file__).resolve().parents[4] / "alembic.ini")
        return cls(
            settings=DatabaseSettings.from_env(),
            alembic_config_path=Path(
                os.environ.get("ODOO_AI_ALEMBIC_CONFIG", default_alembic_config)
            ),
        )

    def inspect(
        self, *, reasoning: ReasoningComponentStatus | None = None
    ) -> AdminStatus:
        database = ComponentStatus(state=ComponentState.ERROR, detail="unavailable")
        migrations = MigrationStatus(state=ComponentState.ERROR, detail="unavailable")
        instance: InstanceStatus | None = None
        engine: Engine | None = None
        reasoning_status = reasoning or ReasoningComponentStatus(
            state=ComponentState.PENDING,
            detail="unknown",
        )

        try:
            engine = create_database_engine(self._settings)
            with engine.connect() as connection:
                connection.execute(select(1))
                database = ComponentStatus(state=ComponentState.OK, detail="available")
                migrations = self._inspect_migrations(connection)
                if migrations.state is ComponentState.OK:
                    instance = self._read_instance(connection, reasoning_status)
        except (CommandError, SQLAlchemyError, OSError, ValueError):
            pass
        finally:
            if engine is not None:
                engine.dispose()

        has_error = (
            database.state is ComponentState.ERROR or migrations.state is ComponentState.ERROR
        )
        source = self._source_status(instance)
        logs = self._log_status(instance)
        pending_capabilities = tuple(
            capability
            for capability in self._PENDING_CAPABILITIES
            if (capability != "source" or source.state is not ComponentState.OK)
            and (capability != "logs" or logs.state is not ComponentState.OK)
            and (
                capability != "reasoning_engine"
                or reasoning_status.state is not ComponentState.OK
            )
        )
        fully_ready = (
            not has_error
            and source.state is ComponentState.OK
            and logs.state is ComponentState.OK
            and reasoning_status.state is ComponentState.OK
        )
        workflow_capabilities = self._workflow_capabilities(
            database=database,
            migrations=migrations,
            instance=instance,
            reasoning=reasoning_status,
        )
        return AdminStatus(
            readiness="ERROR" if has_error else "FULLY_READY" if fully_ready else "DEGRADED",
            checked_at=datetime.now(UTC),
            components=RuntimeComponents(
                runtime=ComponentStatus(state=ComponentState.OK, detail="running"),
                assistant_database=database,
                migrations=migrations,
                source=source,
                logs=logs,
                reasoning_engine=reasoning_status,
            ),
            workflow_capabilities=workflow_capabilities,
            pending_capabilities=pending_capabilities,
            instance=instance,
        )

    def _inspect_migrations(self, connection: Connection) -> MigrationStatus:
        config = Config(self._alembic_config_path)
        expected = ScriptDirectory.from_config(config).get_current_head()
        current = MigrationContext.configure(connection).get_current_revision()
        matches = current is not None and current == expected
        return MigrationStatus(
            state=ComponentState.OK if matches else ComponentState.ERROR,
            detail="at_head" if matches else "revision_mismatch",
            current_revision=current,
            expected_revision=expected,
        )

    @staticmethod
    def _read_instance(
        connection: Connection, reasoning: ReasoningComponentStatus
    ) -> InstanceStatus | None:
        with Session(bind=connection) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                return None
            snapshot = record_reasoning_capability(
                session,
                instance_profile_id=profile.id,
                state=_reasoning_snapshot_state(reasoning),
                provider=reasoning.provider,
                protocol=reasoning.protocol,
                runtime_version=reasoning.runtime_version,
                model=reasoning.model,
            )
            session.commit()
            return InstanceStatus(
                instance_id=profile.instance_id,
                fingerprint=profile.fingerprint,
                reported_readiness=snapshot.readiness if snapshot else None,
                capabilities=_public_capabilities(snapshot.capabilities if snapshot else {}),
            )

    @staticmethod
    def _source_status(instance: InstanceStatus | None) -> ComponentStatus:
        if instance is None:
            return ComponentStatus(state=ComponentState.PENDING, detail="unknown")
        state = instance.capabilities.get("source")
        if state == "DETECTED":
            return ComponentStatus(state=ComponentState.OK, detail="operational")
        if state == "NOT_FOUND":
            return ComponentStatus(state=ComponentState.PENDING, detail="not_found")
        if state == "NO_PERMISSION":
            return ComponentStatus(state=ComponentState.ERROR, detail="no_permission")
        if state == "ERROR":
            return ComponentStatus(state=ComponentState.ERROR, detail="error")
        return ComponentStatus(state=ComponentState.PENDING, detail="unknown")

    @staticmethod
    def _log_status(instance: InstanceStatus | None) -> ComponentStatus:
        if instance is None:
            return ComponentStatus(state=ComponentState.PENDING, detail="unknown")
        state = instance.capabilities.get("logs")
        if state == "OPERATIONAL":
            return ComponentStatus(state=ComponentState.OK, detail="operational")
        if state == "NOT_FOUND":
            return ComponentStatus(state=ComponentState.PENDING, detail="not_found")
        if state == "NO_PERMISSION":
            return ComponentStatus(state=ComponentState.ERROR, detail="no_permission")
        if state == "ERROR":
            return ComponentStatus(state=ComponentState.ERROR, detail="error")
        return ComponentStatus(state=ComponentState.PENDING, detail="unknown")

    @staticmethod
    def _workflow_capabilities(
        *,
        database: ComponentStatus,
        migrations: MigrationStatus,
        instance: InstanceStatus | None,
        reasoning: ReasoningComponentStatus,
    ) -> WorkflowCapabilities:
        if (
            database.state is not ComponentState.OK
            or migrations.state is not ComponentState.OK
        ):
            unavailable = ComponentStatus(
                state=ComponentState.ERROR,
                detail="assistant_runtime_unavailable",
            )
            return WorkflowCapabilities(
                query=unavailable,
                navigation=unavailable,
                knowledge=unavailable,
                how_to=unavailable,
            )

        navigation = ComponentStatus(
            state=ComponentState.OK,
            detail="validated_per_turn",
        )
        knowledge = ComponentStatus(
            state=(
                ComponentState.OK
                if instance is not None
                else ComponentState.PENDING
            ),
            detail="available" if instance is not None else "instance_unknown",
        )
        query = ComponentStatus(
            state=(
                ComponentState.OK
                if reasoning.state is ComponentState.OK
                else ComponentState.PENDING
            ),
            detail=(
                "validated_per_turn"
                if reasoning.state is ComponentState.OK
                else "reasoning_unavailable"
            ),
        )
        how_to_ready = (
            reasoning.state is ComponentState.OK
            and knowledge.state is ComponentState.OK
        )
        return WorkflowCapabilities(
            query=query,
            navigation=navigation,
            knowledge=knowledge,
            how_to=ComponentStatus(
                state=(
                    ComponentState.OK
                    if how_to_ready
                    else ComponentState.PENDING
                ),
                detail=(
                    "validated_per_turn"
                    if how_to_ready
                    else (
                        "reasoning_unavailable"
                        if reasoning.state is not ComponentState.OK
                        else "knowledge_unavailable"
                    )
                ),
            ),
        )


def unavailable_admin_status() -> AdminStatus:
    """Return a sanitized status when external configuration cannot be loaded."""

    unavailable = ComponentStatus(
        state=ComponentState.ERROR,
        detail="assistant_runtime_unavailable",
    )
    return AdminStatus(
        readiness="ERROR",
        checked_at=datetime.now(UTC),
        components=RuntimeComponents(
            runtime=ComponentStatus(state=ComponentState.OK, detail="running"),
            assistant_database=ComponentStatus(
                state=ComponentState.ERROR, detail="configuration_invalid"
            ),
            migrations=MigrationStatus(state=ComponentState.ERROR, detail="unavailable"),
            source=ComponentStatus(state=ComponentState.PENDING, detail="unknown"),
            logs=ComponentStatus(state=ComponentState.PENDING, detail="unknown"),
            reasoning_engine=ReasoningComponentStatus(
                state=ComponentState.PENDING,
                detail="unknown",
            ),
        ),
        workflow_capabilities=WorkflowCapabilities(
            query=unavailable,
            navigation=unavailable,
            knowledge=unavailable,
            how_to=unavailable,
        ),
        pending_capabilities=AdminStatusService._PENDING_CAPABILITIES,
    )


def inspect_admin_status(
    *, reasoning: ReasoningComponentStatus | None = None
) -> AdminStatus:
    """Build the default status without leaking configuration errors."""

    try:
        return AdminStatusService.from_env().inspect(reasoning=reasoning)
    except DatabaseConfigurationError:
        return unavailable_admin_status()


def _reasoning_snapshot_state(reasoning: ReasoningComponentStatus) -> Literal[
    "OPERATIONAL",
    "NOT_CONFIGURED",
    "RUNTIME_MISSING",
    "AUTH_UNAVAILABLE",
    "PROTOCOL_INCOMPATIBLE",
    "ERROR",
]:
    if reasoning.state is ComponentState.OK:
        return "OPERATIONAL"
    if reasoning.detail == "not_configured":
        return "NOT_CONFIGURED"
    if reasoning.detail == "runtime_missing":
        return "RUNTIME_MISSING"
    if reasoning.detail == "auth_unavailable":
        return "AUTH_UNAVAILABLE"
    if reasoning.detail == "protocol_incompatible":
        return "PROTOCOL_INCOMPATIBLE"
    return "ERROR"


_PUBLIC_CAPABILITY_KEYS = frozenset(
    {
        "assistant_db",
        "log_provider",
        "logs",
        "logs_operational",
        "reasoning_engine",
        "reasoning_model",
        "reasoning_operational",
        "reasoning_protocol",
        "reasoning_provider",
        "reasoning_runtime_version",
        "runtime_http",
        "source",
        "source_operational",
    }
)


def _public_capabilities(
    capabilities: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return {
        key: value
        for key, value in capabilities.items()
        if key in _PUBLIC_CAPABILITY_KEYS
        and not isinstance(value, (dict, list))
        and (not isinstance(value, str) or len(value) <= 128)
    }
