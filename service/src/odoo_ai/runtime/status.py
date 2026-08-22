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
    get_latest_capability_snapshot,
    get_latest_instance_profile,
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


class AdminStatus(BaseModel):
    """Stable admin payload that cannot claim full product readiness in M1."""

    model_config = ConfigDict(frozen=True)

    readiness: Literal["DEGRADED", "ERROR"]
    checked_at: datetime
    components: RuntimeComponents
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

    def inspect(self) -> AdminStatus:
        database = ComponentStatus(state=ComponentState.ERROR, detail="unavailable")
        migrations = MigrationStatus(state=ComponentState.ERROR, detail="unavailable")
        instance: InstanceStatus | None = None
        engine: Engine | None = None

        try:
            engine = create_database_engine(self._settings)
            with engine.connect() as connection:
                connection.execute(select(1))
                database = ComponentStatus(state=ComponentState.OK, detail="available")
                migrations = self._inspect_migrations(connection)
                if migrations.state is ComponentState.OK:
                    instance = self._read_instance(connection)
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
        )
        return AdminStatus(
            readiness="ERROR" if has_error else "DEGRADED",
            checked_at=datetime.now(UTC),
            components=RuntimeComponents(
                runtime=ComponentStatus(state=ComponentState.OK, detail="running"),
                assistant_database=database,
                migrations=migrations,
                source=source,
                logs=logs,
            ),
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
    def _read_instance(connection: Connection) -> InstanceStatus | None:
        with Session(bind=connection) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                return None
            snapshot = get_latest_capability_snapshot(session, instance_profile_id=profile.id)
            return InstanceStatus(
                instance_id=profile.instance_id,
                fingerprint=profile.fingerprint,
                reported_readiness=snapshot.readiness if snapshot else None,
                capabilities=snapshot.capabilities if snapshot else {},
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


def unavailable_admin_status() -> AdminStatus:
    """Return a sanitized status when external configuration cannot be loaded."""

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
        ),
        pending_capabilities=AdminStatusService._PENDING_CAPABILITIES,
    )


def inspect_admin_status() -> AdminStatus:
    """Build the default status without leaking configuration errors."""

    try:
        return AdminStatusService.from_env().inspect()
    except DatabaseConfigurationError:
        return unavailable_admin_status()
