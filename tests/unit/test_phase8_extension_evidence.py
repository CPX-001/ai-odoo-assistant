from __future__ import annotations

from types import SimpleNamespace

from odoo_ai_assistant.runtime.capabilities.context import ContextProviderCatalog
from odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceItem,
    EvidenceKind,
    EvidenceProvider,
    EvidenceProviderCatalog,
)
from odoo_ai_assistant.runtime.capabilities.extensions import (
    AssistantExtensionCatalog,
)
from odoo_ai_assistant.runtime.capabilities.skills import SkillCatalog


def _context():
    return SimpleNamespace(
        user_id=7,
        company_ids=(1,),
        group_xmlids=(),
        env=None,
    )


def _provider(provider_id: str, *, enabled: bool = True) -> EvidenceProvider:
    return EvidenceProvider(
        provider_id=provider_id,
        version="1",
        kinds=(EvidenceKind.DOCUMENT,),
        search=lambda _context, _request: (),
        fetch=lambda _context, ref: EvidenceItem(ref=ref),
        default_enabled=enabled,
    )


def test_extension_activation_uses_effective_available_evidence_ids():
    catalog = AssistantExtensionCatalog(
        skills=SkillCatalog(),
        context_providers=ContextProviderCatalog(),
        evidence_providers=EvidenceProviderCatalog(
            (
                _provider("fixture.disabled", enabled=False),
                _provider("fixture.documents"),
            )
        ),
    )

    active = catalog.activate(_context(), capability_names=())

    assert active.evidence_provider_ids == ("fixture.documents",)
    assert active.host_evidence_contract()["provider_ids"] == [
        "fixture.documents"
    ]
    statuses = {
        item.provider_id: item.state for item in active.evidence_statuses
    }
    assert statuses == {
        "fixture.disabled": "unavailable",
        "fixture.documents": "available",
    }


def test_requested_evidence_ids_cannot_reactivate_unavailable_provider():
    catalog = AssistantExtensionCatalog(
        skills=SkillCatalog(),
        context_providers=ContextProviderCatalog(),
        evidence_providers=EvidenceProviderCatalog(
            (
                _provider("fixture.disabled", enabled=False),
                _provider("fixture.documents"),
            )
        ),
    )

    active = catalog.activate(
        _context(),
        capability_names=(),
        evidence_provider_ids=("fixture.disabled", "fixture.documents"),
    )

    assert active.evidence_provider_ids == ("fixture.documents",)
