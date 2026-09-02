from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityRisk,
)
from odoo_ai_assistant.runtime.capabilities.evidence import (
    LEDGER_MAX_REFS,
    REDACTED_SECRET,
    EvidenceAccessScope,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceKind,
    EvidenceLedger,
    EvidenceLedgerSnapshot,
    EvidenceLocator,
    EvidenceProvider,
    EvidenceProviderCatalog,
    EvidenceRef,
    EvidenceRoutingPolicy,
    EvidenceSearchRequest,
    EvidenceTrust,
    freeze_json_mapping,
)
from odoo_ai_assistant.runtime.capabilities.provider import (
    CAPABILITY_PROVIDER_API_VERSION,
    CapabilityProvider,
)
from odoo_ai_assistant.runtime.capabilities.registry import (
    CapabilityRegistry,
    compose_capability_registry,
)

_EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _context(user_id: int = 7):
    return SimpleNamespace(
        user_id=user_id,
        company_ids=(1,),
        group_xmlids=("base.group_user",),
        env=None,
    )


def _definition(name: str) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description=f"Fixture capability {name}.",
        input_schema=_EMPTY_SCHEMA,
        output_schema={"type": "object"},
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        handler=lambda _context, _arguments: {"ok": True},
    )


def _ref(
    *,
    evidence_id: str = "fixture:runtime:current",
    provider_id: str = "fixture.runtime",
    fingerprint: str = "a" * 64,
    user_id: int = 7,
    conflict_group: str = "",
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        kind=EvidenceKind.RUNTIME,
        provider_id=provider_id,
        locator=EvidenceLocator(
            provider_id=provider_id,
            source_id="fixture.runtime",
            key="current",
        ),
        title="Fixture runtime evidence",
        provenance="deterministic fixture",
        fingerprint=fingerprint,
        captured_at=datetime.now(UTC),
        freshness=EvidenceFreshness.CURRENT,
        trust=EvidenceTrust.HOST_FACT,
        access_scope=EvidenceAccessScope(
            user_id=user_id,
            company_ids=(1,),
            group_xmlids=("base.group_user",),
        ),
        conflict_group=conflict_group,
    )


def _provider(
    provider_id: str,
    *,
    guard=None,
    broken_search: bool = False,
) -> EvidenceProvider:
    def search(_context, _request):
        if broken_search:
            raise RuntimeError("provider exploded")
        return (
            _ref(
                provider_id=provider_id,
                evidence_id=f"{provider_id}:current",
            ),
        )

    def fetch(_context, ref):
        return EvidenceItem(ref=ref, excerpt="bounded", data={"ok": True})

    return EvidenceProvider(
        provider_id=provider_id,
        version="1",
        kinds=(EvidenceKind.RUNTIME,),
        search=search,
        fetch=fetch,
        guard=guard,
    )


def test_json_and_provider_metadata_are_deeply_immutable_secret_safe_and_container_compatible():
    original = {
        "nested": {"values": [1, 2]},
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
    }
    frozen = freeze_json_mapping(original)
    original["nested"]["values"].append(3)

    assert isinstance(frozen, dict)
    assert isinstance(frozen["nested"], dict)
    assert isinstance(frozen["nested"]["values"], list)
    assert frozen["nested"]["values"] == [1, 2]
    assert frozen["api_key"] == REDACTED_SECRET
    with pytest.raises(TypeError):
        frozen["new"] = True
    with pytest.raises(TypeError):
        frozen["nested"]["values"].append(3)

    provider = CapabilityProvider(
        provider_id="vendor.fixture",
        metadata={"nested": {"enabled": True}},
    )
    assert isinstance(provider.metadata, dict)
    with pytest.raises(TypeError):
        provider.metadata["nested"]["enabled"] = False


def test_capability_provider_api_mismatch_is_isolated_instead_of_breaking_healthy_sibling():
    incompatible = CapabilityProvider(
        provider_id="vendor.incompatible",
        api_version="999",
    )
    healthy = CapabilityProvider(provider_id="vendor.healthy")

    registry = compose_capability_registry(
        CapabilityRegistry(),
        (incompatible, healthy),
    )
    status = {item.provider_id: item for item in registry.provider_statuses}

    assert status["vendor.incompatible"].state == "failed"
    assert status["vendor.incompatible"].api_version == "999"
    assert (
        status["vendor.incompatible"].error_code
        == "capability_provider_api_version_incompatible"
    )
    assert status["vendor.healthy"].state == "loaded"
    assert status["vendor.healthy"].api_version == CAPABILITY_PROVIDER_API_VERSION


def test_reserved_provider_and_resource_namespaces_are_isolated_for_third_parties():
    reserved_provider = CapabilityProvider(provider_id="assistant.fixture")
    reserved_resource = CapabilityProvider(
        provider_id="vendor.fixture",
        definitions=(_definition("assistant.hidden_probe"),),
    )
    healthy = CapabilityProvider(provider_id="vendor.healthy")

    registry = compose_capability_registry(
        CapabilityRegistry(),
        (reserved_provider, reserved_resource, healthy),
    )
    status = {item.provider_id: item for item in registry.provider_statuses}

    assert status["assistant.fixture"].error_code == "capability_provider_namespace_reserved"
    assert (
        status["vendor.fixture"].error_code
        == "capability_provider_resource_namespace_reserved"
    )
    assert status["vendor.healthy"].state == "loaded"

    core = CapabilityProvider(
        provider_id="assistant.fixture",
        metadata={"namespace_owner": "core"},
        api_version=CAPABILITY_PROVIDER_API_VERSION,
    )
    core_registry = compose_capability_registry(CapabilityRegistry(), (core,))
    assert core_registry.provider_statuses[0].state == "loaded"


def test_guard_exception_isolated_and_healthy_evidence_provider_survives():
    def exploding_guard(_context):
        raise RuntimeError("guard failure")

    catalog = EvidenceProviderCatalog(
        (
            _provider("fixture.broken_guard", guard=exploding_guard),
            _provider("fixture.healthy"),
        )
    )
    available, statuses = catalog.availability(_context())

    assert tuple(item.provider_id for item in available) == ("fixture.healthy",)
    status = {item.provider_id: item for item in statuses}
    assert status["fixture.broken_guard"].state == "unavailable"
    assert (
        status["fixture.broken_guard"].error_code
        == "evidence_provider_guard_exception"
    )
    assert status["fixture.healthy"].state == "available"


def test_broken_optional_search_does_not_remove_healthy_results():
    catalog = EvidenceProviderCatalog(
        (
            _provider("fixture.broken", broken_search=True),
            _provider("fixture.healthy"),
        )
    )
    batch = catalog.search(
        _context(),
        EvidenceSearchRequest(
            query="inspect runtime",
            kinds=(EvidenceKind.RUNTIME,),
        ),
    )

    assert tuple(item.evidence_id for item in batch.refs) == (
        "fixture.healthy:current",
    )
    status = {item.provider_id: item for item in batch.statuses}
    assert status["fixture.broken"].state == "failed"
    assert status["fixture.healthy"].state == "available"


def test_access_scope_is_checked_again_on_fetch():
    catalog = EvidenceProviderCatalog((_provider("fixture.runtime"),))
    ref = catalog.search(
        _context(7),
        EvidenceSearchRequest(
            query="runtime",
            kinds=(EvidenceKind.RUNTIME,),
        ),
    ).refs[0]

    assert catalog.fetch(_context(7), ref).excerpt == "bounded"
    with pytest.raises(CapabilityError, match="evidence_access_denied"):
        catalog.fetch(_context(8), ref)


def test_ledger_deduplicates_restores_and_preserves_conflicts():
    ledger = EvidenceLedger()
    first = _ref(conflict_group="configuration.answer")
    item = EvidenceItem(
        ref=first,
        excerpt="evidence excerpt",
        data={"token": "Bearer abcdefghijklmnopqrstuvwxyz"},
    )
    ledger.register(item)
    ledger.register(first)

    snapshot = ledger.snapshot()
    assert len(snapshot.refs) == 1
    assert len(snapshot.items) == 1
    assert snapshot.refs[0].conflict_group == "configuration.answer"
    assert REDACTED_SECRET in snapshot.items[0].data["token"]

    restored_snapshot = EvidenceLedgerSnapshot.from_json_value(
        snapshot.to_json_value()
    )
    restored = EvidenceLedger(restored_snapshot).snapshot()
    assert restored.to_json_value() == restored_snapshot.to_json_value()


def test_ledger_rejects_identity_conflicts_and_overflow_transactionally():
    ledger = EvidenceLedger()
    original = _ref()
    ledger.register(original)
    conflicting = replace(
        original,
        locator=EvidenceLocator(
            provider_id=original.provider_id,
            source_id="fixture.runtime",
            key="different",
        ),
    )
    with pytest.raises(
        CapabilityError,
        match="evidence_ledger_identity_conflict",
    ):
        ledger.register(conflicting)
    assert len(ledger.snapshot().refs) == 1

    full = EvidenceLedger()
    for index in range(LEDGER_MAX_REFS):
        full.register(_ref(evidence_id=f"fixture:runtime:{index:03d}"))
    before = full.snapshot().to_json_value()
    with pytest.raises(
        CapabilityError,
        match="evidence_ledger_ref_limit_exceeded",
    ):
        full.register(_ref(evidence_id="fixture:runtime:overflow"))
    assert full.snapshot().to_json_value() == before


def test_routing_prioritizes_installation_evidence_and_skips_generic_turns():
    runtime = _provider("fixture.runtime")
    document = EvidenceProvider(
        provider_id="fixture.documents",
        version="1",
        kinds=(EvidenceKind.DOCUMENT,),
        search=lambda _context, _request: (),
        fetch=lambda _context, ref: EvidenceItem(ref=ref),
    )
    policy = EvidenceRoutingPolicy()
    selected = policy.select(
        EvidenceSearchRequest(query="qué módulos hay instalados"),
        (document, runtime),
    )

    assert selected[0].provider_id == "fixture.runtime"
    assert policy.select(EvidenceSearchRequest(query="hola, gracias"), (document, runtime)) == ()
