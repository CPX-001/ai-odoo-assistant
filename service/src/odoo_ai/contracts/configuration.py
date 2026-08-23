"""Typed M7 configuration contracts, provenance resolution, and path boundaries."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIG_SCHEMA_VERSION = 1


class ConfigScope(StrEnum):
    """Runtime boundary that owns or consumes one configuration key."""

    HOST = "host"
    ODOO = "odoo"
    ASSISTANT = "assistant"
    DISCOVERY = "discovery"


class ConfigOwnership(StrEnum):
    """Who is allowed to change a configuration value."""

    HOST_ONLY = "host_only"
    ADMIN_MUTABLE = "admin_mutable"
    DISCOVERED = "discovered"


class ConfigProvenance(StrEnum):
    """Ordered evidence sources used to resolve effective configuration."""

    EXPLICIT_OVERRIDE = "explicit_override"
    RUNTIME = "runtime"
    SUPERVISOR = "supervisor"
    CONFIG = "config"
    HINT = "hint"
    UNKNOWN = "unknown"


class ConfigSensitivity(StrEnum):
    """How an effective value may be exposed to an Odoo system administrator."""

    PUBLIC = "public"
    ADMIN_ONLY = "admin_only"
    SECRET_REFERENCE = "secret_reference"
    SECRET = "secret"


class ConfigReloadMode(StrEnum):
    """Operational action required after a valid configuration change."""

    HOT = "hot"
    RESTART_REQUIRED = "restart_required"
    SETUP_REQUIRED = "setup_required"
    READ_ONLY = "read_only"


class ConfigValidationState(StrEnum):
    """Validation state of one effective configuration value."""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class ConfigValueState(StrEnum):
    """Distinguish unknown from a known-but-empty effective value."""

    VALUE = "value"
    EMPTY = "empty"
    UNKNOWN = "unknown"


ConfigValueData = str | int | float | bool | tuple[str, ...] | None


class ConfigDescriptor(BaseModel):
    """Stable metadata for one configuration key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    version: int = Field(default=CONFIG_SCHEMA_VERSION, ge=1)
    scope: ConfigScope
    ownership: ConfigOwnership
    value_kind: str = Field(min_length=1, max_length=32)
    sensitivity: ConfigSensitivity
    reload_mode: ConfigReloadMode
    consumer: str = Field(min_length=1, max_length=128)
    envelope_key: str | None = Field(default=None, max_length=128)
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    readonly_reason: str | None = Field(default=None, max_length=240)


class ConfigCandidate(BaseModel):
    """One typed observation that may contribute to an effective value."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    value: ConfigValueData = None
    present: bool = True
    provenance: ConfigProvenance
    validation_state: ConfigValidationState = ConfigValidationState.VALID
    validation_message: str | None = Field(default=None, max_length=240)


class EffectiveConfigValue(BaseModel):
    """Sanitized effective value with provenance and validation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    descriptor_version: int
    ownership: ConfigOwnership
    sensitivity: ConfigSensitivity
    reload_mode: ConfigReloadMode
    value_state: ConfigValueState
    effective_value: ConfigValueData
    provenance: ConfigProvenance
    validation_state: ConfigValidationState
    validation_message: str | None = None
    readonly_reason: str | None = None


class EffectiveConfigSnapshot(BaseModel):
    """Deterministic, admin-safe configuration snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = CONFIG_SCHEMA_VERSION
    fingerprint: str
    values: tuple[EffectiveConfigValue, ...]


class PathEnvelope(BaseModel):
    """Host-authorized filesystem envelope used by mutable path selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=128)
    roots: tuple[str, ...] = Field(min_length=1)
    allow_descendants: bool = True


class AssistantAdminOverrides(BaseModel):
    """Complete bounded set of Assistant-side ADMIN_MUTABLE overrides."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_roots: tuple[str, ...] | None = None
    log_provider: Literal["auto", "file", "journal"] | None = None
    reasoning_model: str | None = Field(default=None, min_length=1, max_length=128)
    reasoning_startup_timeout_seconds: float | None = Field(default=None, ge=1.0, le=120.0)
    reasoning_turn_timeout_seconds: float | None = Field(default=None, ge=5.0, le=600.0)

    @field_validator("source_roots")
    @classmethod
    def _normalize_source_roots(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        normalized = tuple(item.strip() for item in value)
        if not normalized:
            return ()
        if any(not item for item in normalized):
            raise ValueError("source_roots must not contain empty paths")
        if len(set(normalized)) != len(normalized):
            raise ValueError("source_roots must not contain duplicates")
        if len(normalized) > 32:
            raise ValueError("source_roots exceeds the bounded maximum")
        return normalized

    @field_validator("reasoning_model")
    @classmethod
    def _validate_reasoning_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("reasoning_model must not be empty")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-")
        if any(character not in allowed for character in normalized):
            raise ValueError("reasoning_model contains unsupported characters")
        return normalized


class ConfigBoundaryError(ValueError):
    """Raised when a mutable path escapes a host-owned envelope."""


_PROVENANCE_PRIORITY = {
    ConfigProvenance.EXPLICIT_OVERRIDE: 60,
    ConfigProvenance.RUNTIME: 50,
    ConfigProvenance.SUPERVISOR: 40,
    ConfigProvenance.CONFIG: 30,
    ConfigProvenance.HINT: 20,
    ConfigProvenance.UNKNOWN: 0,
}


CONFIG_CATALOG: tuple[ConfigDescriptor, ...] = tuple(
    sorted(
        (
            ConfigDescriptor(
                key="connection.machine_credential",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="secret_reference",
                sensitivity=ConfigSensitivity.SECRET_REFERENCE,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="odoo.assistant_client",
                readonly_reason="Provisioned by setup; Odoo may only report whether it is configured.",
            ),
            ConfigDescriptor(
                key="connection.service_url",
                scope=ConfigScope.ODOO,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="url",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.HOT,
                consumer="odoo.assistant_client",
            ),
            ConfigDescriptor(
                key="host.bind_host",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="string",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.uvicorn",
                readonly_reason="Loopback binding is a host security boundary.",
            ),
            ConfigDescriptor(
                key="host.bind_port",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="integer",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.uvicorn",
                readonly_reason="Listener changes remain in setup/bootstrap.",
            ),
            ConfigDescriptor(
                key="host.database_url",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="secret",
                sensitivity=ConfigSensitivity.SECRET,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.storage",
                readonly_reason="Assistant database credentials remain host-owned.",
            ),
            ConfigDescriptor(
                key="host.runtime_root",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="path",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.bootstrap",
                readonly_reason="Runtime layout is selected by setup, not by Odoo.",
            ),
            ConfigDescriptor(
                key="host.service_unit",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="string",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.bootstrap",
                readonly_reason="Supervisor identity remains host-owned.",
            ),
            ConfigDescriptor(
                key="knowledge.provider",
                scope=ConfigScope.DISCOVERY,
                ownership=ConfigOwnership.DISCOVERED,
                value_kind="string",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.READ_ONLY,
                consumer="assistant.knowledge",
                readonly_reason="M5 retrieval uses the provisioned Assistant PostgreSQL index.",
            ),
            ConfigDescriptor(
                key="logs.authorized_file",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="path",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.logs",
                readonly_reason="Setup defines the only file-log candidate.",
            ),
            ConfigDescriptor(
                key="logs.authorized_unit",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="string",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.logs",
                readonly_reason="Setup defines the only journal unit candidate.",
            ),
            ConfigDescriptor(
                key="logs.provider",
                scope=ConfigScope.ASSISTANT,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="choice",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.HOT,
                consumer="assistant.logs",
                choices=("auto", "file", "journal"),
            ),
            ConfigDescriptor(
                key="odoo.addons_roots",
                scope=ConfigScope.DISCOVERY,
                ownership=ConfigOwnership.DISCOVERED,
                value_kind="path_list",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.READ_ONLY,
                consumer="odoo.runtime_inventory",
                readonly_reason="Reported by the Odoo runtime and never trusted as a host privilege grant.",
            ),
            ConfigDescriptor(
                key="odoo.database",
                scope=ConfigScope.DISCOVERY,
                ownership=ConfigOwnership.DISCOVERED,
                value_kind="string",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.READ_ONLY,
                consumer="odoo.runtime_inventory",
                readonly_reason="Derived from the authenticated Odoo request context.",
            ),
            ConfigDescriptor(
                key="odoo.version",
                scope=ConfigScope.DISCOVERY,
                ownership=ConfigOwnership.DISCOVERED,
                value_kind="string",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.READ_ONLY,
                consumer="odoo.runtime_inventory",
                readonly_reason="Reported by the Odoo 18 runtime.",
            ),
            ConfigDescriptor(
                key="reasoning.executable",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="string",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.codex_runtime",
                readonly_reason="Executable selection stays in the host deployment boundary.",
            ),
            ConfigDescriptor(
                key="reasoning.home",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="path",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.codex_runtime",
                readonly_reason="Codex home is a host-owned filesystem boundary.",
            ),
            ConfigDescriptor(
                key="reasoning.model",
                scope=ConfigScope.ASSISTANT,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="string",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.HOT,
                consumer="assistant.codex_runtime",
            ),
            ConfigDescriptor(
                key="reasoning.startup_timeout_seconds",
                scope=ConfigScope.ASSISTANT,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="float",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.HOT,
                consumer="assistant.codex_runtime",
                minimum=1.0,
                maximum=120.0,
            ),
            ConfigDescriptor(
                key="reasoning.turn_timeout_seconds",
                scope=ConfigScope.ASSISTANT,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="float",
                sensitivity=ConfigSensitivity.PUBLIC,
                reload_mode=ConfigReloadMode.HOT,
                consumer="assistant.codex_runtime",
                minimum=5.0,
                maximum=600.0,
            ),
            ConfigDescriptor(
                key="source.authorized_roots",
                scope=ConfigScope.HOST,
                ownership=ConfigOwnership.HOST_ONLY,
                value_kind="path_list",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.SETUP_REQUIRED,
                consumer="assistant.source_scanner",
                readonly_reason="Setup defines the filesystem envelope available to the scanner.",
            ),
            ConfigDescriptor(
                key="source.selected_roots",
                scope=ConfigScope.ASSISTANT,
                ownership=ConfigOwnership.ADMIN_MUTABLE,
                value_kind="path_list",
                sensitivity=ConfigSensitivity.ADMIN_ONLY,
                reload_mode=ConfigReloadMode.HOT,
                consumer="assistant.source_scanner",
                envelope_key="source.authorized_roots",
            ),
        ),
        key=lambda descriptor: descriptor.key,
    )
)

CONFIG_DESCRIPTOR_BY_KEY = {descriptor.key: descriptor for descriptor in CONFIG_CATALOG}


def resolve_config_snapshot(
    candidates: tuple[ConfigCandidate, ...],
) -> EffectiveConfigSnapshot:
    """Resolve candidates by fixed provenance precedence and redact sensitive values."""

    grouped: dict[str, list[ConfigCandidate]] = {}
    seen_sources: set[tuple[str, ConfigProvenance]] = set()
    for candidate in candidates:
        if candidate.key not in CONFIG_DESCRIPTOR_BY_KEY:
            raise ValueError(f"unregistered configuration key: {candidate.key}")
        identity = (candidate.key, candidate.provenance)
        if identity in seen_sources:
            raise ValueError(
                f"duplicate configuration source for {candidate.key}:{candidate.provenance.value}"
            )
        seen_sources.add(identity)
        grouped.setdefault(candidate.key, []).append(candidate)

    values: list[EffectiveConfigValue] = []
    for descriptor in CONFIG_CATALOG:
        available = [candidate for candidate in grouped.get(descriptor.key, ()) if candidate.present]
        if not available:
            values.append(
                EffectiveConfigValue(
                    key=descriptor.key,
                    descriptor_version=descriptor.version,
                    ownership=descriptor.ownership,
                    sensitivity=descriptor.sensitivity,
                    reload_mode=descriptor.reload_mode,
                    value_state=ConfigValueState.UNKNOWN,
                    effective_value=None,
                    provenance=ConfigProvenance.UNKNOWN,
                    validation_state=ConfigValidationState.UNKNOWN,
                    readonly_reason=descriptor.readonly_reason,
                )
            )
            continue
        selected = max(available, key=lambda item: _PROVENANCE_PRIORITY[item.provenance])
        empty = _is_empty(selected.value)
        values.append(
            EffectiveConfigValue(
                key=descriptor.key,
                descriptor_version=descriptor.version,
                ownership=descriptor.ownership,
                sensitivity=descriptor.sensitivity,
                reload_mode=descriptor.reload_mode,
                value_state=ConfigValueState.EMPTY if empty else ConfigValueState.VALUE,
                effective_value=_sanitize_value(descriptor, selected.value),
                provenance=selected.provenance,
                validation_state=selected.validation_state,
                validation_message=selected.validation_message,
                readonly_reason=descriptor.readonly_reason,
            )
        )

    canonical = [
        {
            "key": value.key,
            "descriptor_version": value.descriptor_version,
            "ownership": value.ownership.value,
            "sensitivity": value.sensitivity.value,
            "reload_mode": value.reload_mode.value,
            "value_state": value.value_state.value,
            "effective_value": value.effective_value,
            "provenance": value.provenance.value,
            "validation_state": value.validation_state.value,
            "validation_message": value.validation_message,
        }
        for value in values
    ]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return EffectiveConfigSnapshot(fingerprint=fingerprint, values=tuple(values))


def validate_path_in_envelope(
    candidate: str | Path,
    envelope: PathEnvelope,
    *,
    require_exists: bool = False,
    require_directory: bool = False,
) -> Path:
    """Return one canonical path only when it remains inside a host-owned envelope."""

    raw_candidate = Path(candidate)
    if not raw_candidate.is_absolute():
        raise ConfigBoundaryError("configuration path must be absolute")
    resolved_candidate = raw_candidate.resolve(strict=False)

    if require_exists and not resolved_candidate.exists():
        raise ConfigBoundaryError("configuration path does not exist")
    if require_directory and not resolved_candidate.is_dir():
        raise ConfigBoundaryError("configuration path is not a directory")

    for raw_root in envelope.roots:
        root = Path(raw_root)
        if not root.is_absolute():
            raise ConfigBoundaryError("host envelope contains a non-absolute root")
        resolved_root = root.resolve(strict=False)
        if resolved_candidate == resolved_root:
            return resolved_candidate
        if envelope.allow_descendants and resolved_candidate.is_relative_to(resolved_root):
            return resolved_candidate

    raise ConfigBoundaryError("configuration path escapes the authorized host envelope")


def _sanitize_value(
    descriptor: ConfigDescriptor,
    value: ConfigValueData,
) -> ConfigValueData:
    if _is_empty(value):
        return None if value is None else value
    if descriptor.sensitivity is ConfigSensitivity.SECRET:
        return "<redacted>"
    if descriptor.sensitivity is ConfigSensitivity.SECRET_REFERENCE:
        return "configured"
    return value


def _is_empty(value: ConfigValueData) -> bool:
    return value is None or value == "" or value == ()
