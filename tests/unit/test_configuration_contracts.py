"""Unit coverage for the M7 configuration contract and boundary invariants."""

from pathlib import Path

import pytest
from odoo_ai.contracts.configuration import (
    CONFIG_CATALOG,
    AssistantAdminOverrides,
    ConfigBoundaryError,
    ConfigCandidate,
    ConfigOwnership,
    ConfigProvenance,
    ConfigSensitivity,
    ConfigValueState,
    PathEnvelope,
    resolve_config_snapshot,
    validate_path_in_envelope,
)


def _value(snapshot, key: str):
    return next(item for item in snapshot.values if item.key == key)


def test_catalog_has_explicit_ownership_and_never_exposes_action_policy() -> None:
    assert CONFIG_CATALOG
    assert all(item.ownership in ConfigOwnership for item in CONFIG_CATALOG)
    mutable = {item.key for item in CONFIG_CATALOG if item.ownership is ConfigOwnership.ADMIN_MUTABLE}
    assert mutable == {
        "connection.service_url",
        "logs.provider",
        "reasoning.model",
        "reasoning.startup_timeout_seconds",
        "reasoning.turn_timeout_seconds",
        "source.selected_roots",
    }
    assert not any(key.startswith("action.") for key in mutable)


def test_assistant_override_contract_is_closed_and_typed() -> None:
    parsed = AssistantAdminOverrides.model_validate(
        {
            "source_roots": ["/srv/odoo/addons"],
            "log_provider": "journal",
            "reasoning_model": "gpt-5.6-codex",
            "reasoning_startup_timeout_seconds": 30,
            "reasoning_turn_timeout_seconds": 180,
        }
    )
    assert parsed.source_roots == ("/srv/odoo/addons",)
    with pytest.raises(ValueError):
        AssistantAdminOverrides.model_validate({"host.bind_host": "0.0.0.0"})
    with pytest.raises(ValueError):
        AssistantAdminOverrides.model_validate({"action_handlers": ["generic.call"]})


def test_provenance_resolution_is_deterministic_and_respects_priority() -> None:
    candidates = (
        ConfigCandidate(key="reasoning.model", value="hint-model", provenance=ConfigProvenance.HINT),
        ConfigCandidate(
            key="reasoning.model", value="runtime-model", provenance=ConfigProvenance.RUNTIME
        ),
        ConfigCandidate(
            key="reasoning.model",
            value="admin-model",
            provenance=ConfigProvenance.EXPLICIT_OVERRIDE,
        ),
    )
    forward = resolve_config_snapshot(candidates)
    reverse = resolve_config_snapshot(tuple(reversed(candidates)))

    assert forward == reverse
    selected = _value(forward, "reasoning.model")
    assert selected.effective_value == "admin-model"
    assert selected.provenance is ConfigProvenance.EXPLICIT_OVERRIDE


def test_unknown_is_distinct_from_known_empty_value() -> None:
    unknown = resolve_config_snapshot(())
    empty = resolve_config_snapshot(
        (
            ConfigCandidate(
                key="reasoning.model",
                value="",
                provenance=ConfigProvenance.CONFIG,
            ),
        )
    )

    assert _value(unknown, "reasoning.model").value_state is ConfigValueState.UNKNOWN
    assert _value(empty, "reasoning.model").value_state is ConfigValueState.EMPTY
    assert _value(empty, "reasoning.model").provenance is ConfigProvenance.CONFIG


def test_secret_and_secret_reference_are_redacted_from_snapshot() -> None:
    canary = "opaque-canary-value"
    snapshot = resolve_config_snapshot(
        (
            ConfigCandidate(
                key="host.database_url",
                value=canary,
                provenance=ConfigProvenance.CONFIG,
            ),
            ConfigCandidate(
                key="connection.machine_credential",
                value=f"/etc/odoo-ai/{canary}.ref",
                provenance=ConfigProvenance.CONFIG,
            ),
        )
    )
    rendered = snapshot.model_dump_json()

    assert canary not in rendered
    assert _value(snapshot, "host.database_url").effective_value == "<redacted>"
    assert _value(snapshot, "connection.machine_credential").effective_value == "configured"
    assert (
        next(item for item in CONFIG_CATALOG if item.key == "connection.machine_credential").sensitivity
        is ConfigSensitivity.SECRET_REFERENCE
    )


def test_path_envelope_rejects_relative_outside_and_symlink_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    child = allowed / "addons"
    child.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = allowed / "escape"
    link.symlink_to(outside, target_is_directory=True)
    envelope = PathEnvelope(key="source.authorized_roots", roots=(str(allowed),))

    assert validate_path_in_envelope(child, envelope, require_directory=True) == child.resolve()
    with pytest.raises(ConfigBoundaryError):
        validate_path_in_envelope("relative/addons", envelope)
    with pytest.raises(ConfigBoundaryError):
        validate_path_in_envelope(outside, envelope)
    with pytest.raises(ConfigBoundaryError):
        validate_path_in_envelope(link, envelope)


def test_snapshot_order_and_fingerprint_are_stable() -> None:
    snapshot = resolve_config_snapshot(
        (
            ConfigCandidate(
                key="logs.provider",
                value="auto",
                provenance=ConfigProvenance.CONFIG,
            ),
            ConfigCandidate(
                key="host.bind_port",
                value=8079,
                provenance=ConfigProvenance.SUPERVISOR,
            ),
        )
    )

    keys = [item.key for item in snapshot.values]
    assert keys == sorted(keys)
    assert len(snapshot.fingerprint) == 64
    assert snapshot == resolve_config_snapshot(
        (
            ConfigCandidate(
                key="host.bind_port",
                value=8079,
                provenance=ConfigProvenance.SUPERVISOR,
            ),
            ConfigCandidate(
                key="logs.provider",
                value="auto",
                provenance=ConfigProvenance.CONFIG,
            ),
        )
    )


def test_nondefault_host_layout_is_data_not_application_constant(tmp_path: Path) -> None:
    unusual_root = tmp_path / "tenant-zeta" / "custom-modules"
    unusual_root.mkdir(parents=True)
    envelope = PathEnvelope(
        key="source.authorized_roots",
        roots=(str(tmp_path / "tenant-zeta"),),
    )

    assert validate_path_in_envelope(unusual_root, envelope) == unusual_root.resolve()
