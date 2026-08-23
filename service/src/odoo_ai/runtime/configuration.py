"""M7 runtime configuration validation, persistence, and effective-state resolution."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.contracts.admin_configuration import (
    AdminConfigurationActor,
    AdminConfigurationAuthorized,
    AdminConfigurationResponse,
)
from odoo_ai.contracts.configuration import (
    CONFIG_DESCRIPTOR_BY_KEY,
    AssistantAdminOverrides,
    ConfigCandidate,
    ConfigProvenance,
    ConfigReloadMode,
    ConfigValidationState,
    ConfigValueData,
    PathEnvelope,
    resolve_config_snapshot,
    validate_path_in_envelope,
)
from odoo_ai.logs.common import LogProviderError
from odoo_ai.logs.journal import JournalUnitSelection, resolve_journal_unit
from odoo_ai.logs.resolution import LogFileSelection, resolve_log_file
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from odoo_ai.storage.configuration_repository import (
    LockedRuntimeConfiguration,
    RuntimeConfigStoreError,
    persist_runtime_configuration,
    read_runtime_configuration,
)

SOURCE_ROOTS_ENV = "ODOO_AI_SOURCE_ROOTS"
LOG_FILE_ENV = "ODOO_AI_LOG_FILE"
JOURNAL_UNIT_ENV = "ODOO_AI_JOURNAL_UNIT"
SHARED_SECRET_FILE_ENV = "ODOO_AI_SHARED_SECRET_FILE"
HOST_ENV = "ODOO_AI_HOST"
PORT_ENV = "ODOO_AI_PORT"
DATABASE_URL_ENV = "ODOO_AI_DATABASE_URL"
RUNTIME_ROOT_ENV = "ODOO_AI_RUNTIME_ROOT"
SERVICE_UNIT_ENV = "ODOO_AI_SERVICE_UNIT"
CODEX_EXECUTABLE_ENV = "ODOO_AI_CODEX_EXECUTABLE"
CODEX_HOME_ENV = "ODOO_AI_CODEX_HOME"
CODEX_MODEL_ENV = "ODOO_AI_CODEX_MODEL"
CODEX_STARTUP_TIMEOUT_ENV = "ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS"
CODEX_TURN_TIMEOUT_ENV = "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS"

PostAction = Literal["none", "restart_required", "setup_required"]
LogProviderChoice = Literal["auto", "file", "journal"]

_OVERRIDE_FIELD_TO_KEY = {
    "source_roots": "source.selected_roots",
    "log_provider": "logs.provider",
    "reasoning_model": "reasoning.model",
    "reasoning_startup_timeout_seconds": "reasoning.startup_timeout_seconds",
    "reasoning_turn_timeout_seconds": "reasoning.turn_timeout_seconds",
}
_ADMIN_MODEL = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_HOST_MODEL = re.compile(r"^[A-Za-z0-9_.:-]+$")


class RuntimeConfigurationError(ValueError):
    """Sanitized configuration-boundary failure safe for the admin API."""

    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class HostConfigurationFacts:
    candidates: tuple[ConfigCandidate, ...]
    source_roots: tuple[str, ...]
    log_file: str | None
    journal_unit: str | None
    log_providers: tuple[LogProviderChoice, ...]
    invalid_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OverrideValidation:
    overrides: AssistantAdminOverrides
    invalid_keys: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.invalid_keys


class RuntimeConfigurationService:
    """Validate and atomically advance the Assistant's last-known-good config."""

    def __init__(
        self,
        *,
        database_settings: DatabaseSettings,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._database_settings = database_settings
        self._environ = os.environ if environ is None else environ

    @classmethod
    def from_env(cls) -> RuntimeConfigurationService:
        return cls(database_settings=DatabaseSettings.from_env())

    def current_revision(self) -> int:
        return self._read_current().revision

    def current_overrides(self) -> AssistantAdminOverrides:
        locked = self._read_current()
        facts = _host_facts(self._environ)
        validation = _validate_overrides(_parse_stored_overrides(locked.overrides), facts)
        if facts.invalid_keys or not validation.valid:
            raise RuntimeConfigurationError("configuration_invalid", 422)
        return validation.overrides

    def snapshot(self) -> AdminConfigurationResponse:
        locked = self._read_current()
        stored = _parse_stored_overrides(locked.overrides)
        facts = _host_facts(self._environ)
        validation = _validate_overrides(stored, facts)
        invalid = tuple(dict.fromkeys((*facts.invalid_keys, *validation.invalid_keys)))
        return _response(
            revision=locked.revision,
            overrides=validation.overrides if validation.valid else stored,
            facts=facts,
            invalid_keys=invalid,
            post_action="none",
        )

    def validate(self, overrides: AssistantAdminOverrides) -> AdminConfigurationResponse:
        current = self._read_current()
        previous = _parse_stored_overrides(current.overrides)
        facts = _host_facts(self._environ)
        validation = _validate_overrides(overrides, facts)
        if facts.invalid_keys or not validation.valid:
            raise RuntimeConfigurationError("configuration_invalid", 422)
        return _response(
            revision=current.revision,
            overrides=validation.overrides,
            facts=facts,
            invalid_keys=(),
            post_action=_post_action(previous, validation.overrides),
        )

    def apply(
        self,
        *,
        expected_revision: int,
        overrides: AssistantAdminOverrides,
        actor: AdminConfigurationActor,
    ) -> AdminConfigurationResponse:
        facts = _host_facts(self._environ)
        validation = _validate_overrides(overrides, facts)
        if facts.invalid_keys or not validation.valid:
            raise RuntimeConfigurationError("configuration_invalid", 422)

        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            session_factory = create_session_factory(engine)
            with session_scope(session_factory) as session:
                locked = read_runtime_configuration(session, for_update=True)
                if locked.revision != expected_revision:
                    raise RuntimeConfigurationError("configuration_revision_conflict", 409)
                previous = _parse_stored_overrides(locked.overrides)
                canonical = validation.overrides
                response = _response(
                    revision=locked.revision,
                    overrides=canonical,
                    facts=facts,
                    invalid_keys=(),
                    post_action=_post_action(previous, canonical),
                )
                serialized = _serialized_overrides(canonical)
                if serialized == locked.overrides:
                    return response
                persisted = persist_runtime_configuration(
                    session,
                    locked=locked,
                    overrides=serialized,
                    fingerprint=response.fingerprint,
                    actor_uid=actor.odoo_uid,
                    actor_database=actor.odoo_database,
                    changed_keys=_changed_keys(previous, canonical),
                )
                return response.model_copy(update={"revision": persisted.revision})
        except RuntimeConfigurationError:
            raise
        except RuntimeConfigStoreError as error:
            status = 409 if error.code == "configuration_revision_conflict" else 503
            raise RuntimeConfigurationError(error.code, status) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeConfigurationError("configuration_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _read_current(self) -> LockedRuntimeConfiguration:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return read_runtime_configuration(session)
        except RuntimeConfigStoreError as error:
            raise RuntimeConfigurationError(error.code, 503) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeConfigurationError("configuration_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()


def load_runtime_admin_overrides(
    environ: Mapping[str, str] | None = None,
) -> AssistantAdminOverrides:
    """Load persisted overrides without mutating process environment."""

    source = os.environ if environ is None else environ
    if not source.get(DATABASE_URL_ENV):
        return AssistantAdminOverrides()
    try:
        return RuntimeConfigurationService(
            database_settings=DatabaseSettings.from_env(source),
            environ=source,
        ).current_overrides()
    except RuntimeConfigurationError:
        raise
    except (DatabaseConfigurationError, OSError, ValueError):
        raise RuntimeConfigurationError("configuration_unavailable", 503) from None


def current_runtime_config_revision(
    environ: Mapping[str, str] | None = None,
) -> int:
    source = os.environ if environ is None else environ
    if not source.get(DATABASE_URL_ENV):
        return 0
    try:
        return RuntimeConfigurationService(
            database_settings=DatabaseSettings.from_env(source),
            environ=source,
        ).current_revision()
    except RuntimeConfigurationError:
        raise
    except (DatabaseConfigurationError, OSError, ValueError):
        raise RuntimeConfigurationError("configuration_unavailable", 503) from None


def runtime_configuration_is_valid(
    environ: Mapping[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    if not source.get(DATABASE_URL_ENV):
        return False
    try:
        response = RuntimeConfigurationService(
            database_settings=DatabaseSettings.from_env(source),
            environ=source,
        ).snapshot()
    except (RuntimeConfigurationError, DatabaseConfigurationError, OSError, ValueError):
        return False
    return response.validation_state == "valid"


def _host_facts(environ: Mapping[str, str]) -> HostConfigurationFacts:
    candidates: list[ConfigCandidate] = []
    invalid: list[str] = []
    for key, raw in (
        ("host.bind_host", environ.get(HOST_ENV)),
        ("host.database_url", environ.get(DATABASE_URL_ENV)),
        ("host.runtime_root", environ.get(RUNTIME_ROOT_ENV)),
        ("host.service_unit", environ.get(SERVICE_UNIT_ENV)),
        ("reasoning.executable", environ.get(CODEX_EXECUTABLE_ENV)),
        ("reasoning.home", environ.get(CODEX_HOME_ENV)),
    ):
        _append_string_candidate(candidates, key, raw)

    raw_model = environ.get(CODEX_MODEL_ENV)
    model = _bounded_string(raw_model, max_length=128)
    if model is not None and _HOST_MODEL.fullmatch(model):
        candidates.append(_candidate("reasoning.model", model, ConfigProvenance.SUPERVISOR))
    elif raw_model:
        invalid.append("reasoning.model")
        candidates.append(_invalid_candidate("reasoning.model", "invalid_host_model"))

    raw_port = environ.get(PORT_ENV)
    if raw_port:
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
            candidates.append(_candidate("host.bind_port", port, ConfigProvenance.SUPERVISOR))
        except ValueError:
            invalid.append("host.bind_port")
            candidates.append(_invalid_candidate("host.bind_port", "invalid_host_port"))

    source_roots, source_error = _parse_host_source_roots(environ.get(SOURCE_ROOTS_ENV))
    if source_error is not None:
        invalid.append("source.authorized_roots")
        candidates.append(
            _invalid_candidate("source.authorized_roots", "invalid_authorized_source_roots", ())
        )
    elif source_roots:
        candidates.append(
            _candidate("source.authorized_roots", source_roots, ConfigProvenance.SUPERVISOR)
        )
        candidates.append(
            _candidate("source.selected_roots", source_roots, ConfigProvenance.SUPERVISOR)
        )

    raw_log_file = environ.get(LOG_FILE_ENV)
    log_file = _absolute_host_path(raw_log_file)
    if raw_log_file and log_file is None:
        invalid.append("logs.authorized_file")
        candidates.append(_invalid_candidate("logs.authorized_file", "invalid_authorized_log_file"))
    elif log_file is not None:
        candidates.append(
            _candidate("logs.authorized_file", log_file, ConfigProvenance.SUPERVISOR)
        )

    raw_unit = environ.get(JOURNAL_UNIT_ENV)
    journal_unit = _bounded_string(raw_unit, max_length=247)
    if journal_unit is not None:
        try:
            resolved = resolve_journal_unit(JournalUnitSelection(override=(journal_unit,)))
        except LogProviderError:
            resolved = None
        if resolved is None:
            invalid.append("logs.authorized_unit")
            candidates.append(
                _invalid_candidate("logs.authorized_unit", "invalid_authorized_journal_unit")
            )
            journal_unit = None
        else:
            journal_unit = resolved.unit
            candidates.append(
                _candidate("logs.authorized_unit", journal_unit, ConfigProvenance.SUPERVISOR)
            )
    elif raw_unit:
        invalid.append("logs.authorized_unit")

    candidates.append(_candidate("logs.provider", "auto", ConfigProvenance.HINT))
    candidates.append(
        _candidate("knowledge.provider", "postgresql_fts", ConfigProvenance.RUNTIME)
    )
    if _bounded_string(environ.get(SHARED_SECRET_FILE_ENV), max_length=4096) is not None:
        candidates.append(
            _candidate(
                "connection.machine_credential",
                "configured",
                ConfigProvenance.SUPERVISOR,
            )
        )

    # Preserve the pre-M7 host contract. Settings has its own narrower bounds.
    _append_timeout_candidate(
        candidates,
        invalid,
        key="reasoning.startup_timeout_seconds",
        raw=environ.get(CODEX_STARTUP_TIMEOUT_ENV),
        default=5.0,
        minimum=0.0,
        maximum=60.0,
    )
    _append_timeout_candidate(
        candidates,
        invalid,
        key="reasoning.turn_timeout_seconds",
        raw=environ.get(CODEX_TURN_TIMEOUT_ENV),
        default=120.0,
        minimum=0.0,
        maximum=1800.0,
    )

    providers: list[LogProviderChoice] = ["auto"]
    if log_file is not None:
        providers.append("file")
    if journal_unit is not None:
        providers.append("journal")
    return HostConfigurationFacts(
        candidates=tuple(candidates),
        source_roots=source_roots,
        log_file=log_file,
        journal_unit=journal_unit,
        log_providers=tuple(providers),
        invalid_keys=tuple(dict.fromkeys(invalid)),
    )


def _validate_overrides(
    overrides: AssistantAdminOverrides,
    facts: HostConfigurationFacts,
) -> OverrideValidation:
    invalid: list[str] = []
    roots = None if overrides.source_roots == () else overrides.source_roots
    if roots:
        if not facts.source_roots:
            invalid.append("source.selected_roots")
        else:
            envelope = PathEnvelope(key="source.authorized_roots", roots=facts.source_roots)
            resolved_roots: list[str] = []
            for root in roots:
                try:
                    resolved = validate_path_in_envelope(
                        root,
                        envelope,
                        require_exists=True,
                        require_directory=True,
                    )
                except (OSError, ValueError):
                    invalid.append("source.selected_roots")
                    break
                resolved_roots.append(str(resolved))
            else:
                roots = tuple(dict.fromkeys(resolved_roots))

    if overrides.log_provider == "file":
        if facts.log_file is None or resolve_log_file(
            LogFileSelection(override=(facts.log_file,))
        ).resolved is None:
            invalid.append("logs.provider")
    elif overrides.log_provider == "journal":
        if facts.journal_unit is None:
            invalid.append("logs.provider")
        else:
            try:
                resolved_unit = resolve_journal_unit(
                    JournalUnitSelection(override=(facts.journal_unit,))
                )
            except LogProviderError:
                resolved_unit = None
            if resolved_unit is None:
                invalid.append("logs.provider")

    if overrides.reasoning_model is not None and _ADMIN_MODEL.fullmatch(
        overrides.reasoning_model
    ) is None:
        invalid.append("reasoning.model")

    return OverrideValidation(
        overrides=overrides.model_copy(update={"source_roots": roots}),
        invalid_keys=tuple(dict.fromkeys(invalid)),
    )


def _response(
    *,
    revision: int,
    overrides: AssistantAdminOverrides,
    facts: HostConfigurationFacts,
    invalid_keys: tuple[str, ...],
    post_action: PostAction,
) -> AdminConfigurationResponse:
    invalid_set = set(invalid_keys)
    candidates = list(facts.candidates)
    values = overrides.model_dump()
    for field_name, stable_key in _OVERRIDE_FIELD_TO_KEY.items():
        value = cast(ConfigValueData, values[field_name])
        if value is None:
            continue
        candidates.append(
            ConfigCandidate(
                key=stable_key,
                value=value,
                provenance=ConfigProvenance.EXPLICIT_OVERRIDE,
                validation_state=(
                    ConfigValidationState.INVALID
                    if stable_key in invalid_set
                    else ConfigValidationState.VALID
                ),
                validation_message=(
                    "outside_authorized_runtime_boundary" if stable_key in invalid_set else None
                ),
            )
        )
    snapshot = resolve_config_snapshot(tuple(candidates))
    return AdminConfigurationResponse(
        revision=revision,
        fingerprint=snapshot.fingerprint,
        validation_state="invalid" if invalid_keys else "valid",
        post_action=post_action,
        overrides=overrides,
        authorized=AdminConfigurationAuthorized(
            source_roots=facts.source_roots,
            log_providers=facts.log_providers,
        ),
        snapshot=snapshot,
    )


def _post_action(
    previous: AssistantAdminOverrides,
    current: AssistantAdminOverrides,
) -> PostAction:
    modes = {CONFIG_DESCRIPTOR_BY_KEY[key].reload_mode for key in _changed_keys(previous, current)}
    if ConfigReloadMode.SETUP_REQUIRED in modes:
        return "setup_required"
    if ConfigReloadMode.RESTART_REQUIRED in modes:
        return "restart_required"
    return "none"


def _changed_keys(
    previous: AssistantAdminOverrides,
    current: AssistantAdminOverrides,
) -> tuple[str, ...]:
    before = previous.model_dump(mode="json")
    after = current.model_dump(mode="json")
    return tuple(
        _OVERRIDE_FIELD_TO_KEY[field_name]
        for field_name in _OVERRIDE_FIELD_TO_KEY
        if before[field_name] != after[field_name]
    )


def _serialized_overrides(overrides: AssistantAdminOverrides) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], overrides.model_dump(mode="json"))


def _parse_stored_overrides(value: Mapping[str, JsonValue]) -> AssistantAdminOverrides:
    try:
        return AssistantAdminOverrides.model_validate(dict(value))
    except ValidationError:
        raise RuntimeConfigurationError("configuration_persisted_payload_invalid", 503) from None


def _parse_host_source_roots(raw: str | None) -> tuple[tuple[str, ...], str | None]:
    if not raw:
        return (), None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return (), "invalid_json"
    if (
        not isinstance(values, list)
        or len(values) > 128
        or any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 4096
            for value in values
        )
    ):
        return (), "invalid_shape"
    roots: list[str] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            return (), "non_absolute"
        try:
            resolved = str(path.resolve(strict=False))
        except (OSError, RuntimeError):
            return (), "resolution_failed"
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots), None


def _absolute_host_path(raw: str | None) -> str | None:
    value = _bounded_string(raw, max_length=4096)
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    try:
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError):
        return None


def _bounded_string(raw: str | None, *, max_length: int) -> str | None:
    if raw is None or raw == "":
        return None
    if raw != raw.strip() or len(raw) > max_length or any(
        character in raw for character in "\r\n\x00"
    ):
        return None
    return raw


def _candidate(
    key: str,
    value: ConfigValueData,
    provenance: ConfigProvenance,
) -> ConfigCandidate:
    return ConfigCandidate(key=key, value=value, provenance=provenance)


def _invalid_candidate(
    key: str,
    message: str,
    value: ConfigValueData = None,
) -> ConfigCandidate:
    return ConfigCandidate(
        key=key,
        value=value,
        provenance=ConfigProvenance.SUPERVISOR,
        validation_state=ConfigValidationState.INVALID,
        validation_message=message,
    )


def _append_string_candidate(
    candidates: list[ConfigCandidate],
    key: str,
    raw: str | None,
) -> None:
    value = _bounded_string(raw, max_length=4096)
    if value is not None:
        candidates.append(_candidate(key, value, ConfigProvenance.SUPERVISOR))


def _append_timeout_candidate(
    candidates: list[ConfigCandidate],
    invalid: list[str],
    *,
    key: str,
    raw: str | None,
    default: float,
    minimum: float,
    maximum: float,
) -> None:
    if raw is None or raw == "":
        candidates.append(_candidate(key, default, ConfigProvenance.HINT))
        return
    try:
        value = float(raw)
        if not minimum < value <= maximum:
            raise ValueError
    except ValueError:
        invalid.append(key)
        candidates.append(_invalid_candidate(key, "invalid_host_timeout"))
        return
    candidates.append(_candidate(key, value, ConfigProvenance.SUPERVISOR))
