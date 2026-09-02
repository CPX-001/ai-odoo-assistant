from __future__ import annotations

from types import SimpleNamespace

import pytest

from odoo_ai_assistant.runtime.capabilities.context import (
    ContextProvider,
    ContextProviderCatalog,
)
from odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceItem,
    EvidenceKind,
    EvidenceProvider,
    EvidenceProviderCatalog,
)
from odoo_ai_assistant.runtime.capabilities.extensions import (
    AssistantExtensionCatalog,
)
from odoo_ai_assistant.runtime.capabilities.skills import (
    SkillCatalog,
    SkillDefinition,
)


def _context():
    return SimpleNamespace(
        user_id=7,
        company_ids=(1,),
        group_xmlids=(),
        env=None,
        metadata={},
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


def test_skill_evidence_selector_activates_only_from_effective_catalog():
    skill = SkillDefinition(
        skill_id="fixture.document_skill",
        description="Use document Evidence when it is actually available.",
        evidence_provider_selectors=("fixture.documents",),
    )
    catalog = AssistantExtensionCatalog(
        skills=SkillCatalog((skill,)),
        context_providers=ContextProviderCatalog(),
        evidence_providers=EvidenceProviderCatalog(
            (
                _provider("fixture.disabled", enabled=False),
                _provider("fixture.documents"),
            )
        ),
    )

    active = catalog.activate(_context(), capability_names=())

    assert active.skills == (skill,)
    assert active.evidence_provider_ids == ("fixture.documents",)

    unavailable_only = catalog.activate(
        _context(),
        capability_names=(),
        evidence_provider_ids=("fixture.disabled",),
    )
    assert unavailable_only.skills == ()
    assert unavailable_only.evidence_provider_ids == ()


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


def test_skill_and_context_provider_metadata_are_deeply_immutable_dict_list_compatible():
    skill = SkillDefinition(
        skill_id="fixture.immutable_skill",
        description="Immutable metadata fixture.",
        activation_metadata={"nested": {"values": [1, 2]}},
    )
    context_provider = ContextProvider(
        provider_id="fixture.context",
        description="Immutable context metadata fixture.",
        collect=lambda _context: {"nested": {"values": [1, 2]}},
        metadata={"nested": {"values": [1, 2]}},
    )

    assert isinstance(skill.activation_metadata, dict)
    assert isinstance(skill.activation_metadata["nested"]["values"], list)
    assert isinstance(context_provider.metadata, dict)
    with pytest.raises(TypeError):
        skill.activation_metadata["nested"]["values"].append(3)
    with pytest.raises(TypeError):
        context_provider.metadata["nested"]["values"].append(3)

    contributions, _statuses = ContextProviderCatalog((context_provider,)).collect(
        _context(),
        provider_ids=("fixture.context",),
    )
    assert isinstance(contributions[0].data, dict)
    assert isinstance(contributions[0].data["nested"]["values"], list)
    with pytest.raises(TypeError):
        contributions[0].data["nested"]["values"].append(3)
