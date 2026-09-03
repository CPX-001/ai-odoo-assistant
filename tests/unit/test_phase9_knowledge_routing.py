from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ADDON_ROOT = Path(__file__).resolve().parents[2] / "addons/odoo_ai_assistant"
for package_name, package_path in (
    ("addons.odoo_ai_assistant", ADDON_ROOT),
    ("addons.odoo_ai_assistant.runtime", ADDON_ROOT / "runtime"),
    (
        "addons.odoo_ai_assistant.runtime.capabilities",
        ADDON_ROOT / "runtime/capabilities",
    ),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules.setdefault(package_name, package)


evidence = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.evidence"
)
knowledge_routing = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.knowledge_routing"
)

EvidenceKind = evidence.EvidenceKind
EvidenceProvider = evidence.EvidenceProvider
EvidenceSearchResult = evidence.EvidenceSearchResult
EvidenceSearchRequest = evidence.EvidenceSearchRequest
CompanyKnowledgeEvidenceRoutingPolicy = (
    knowledge_routing.CompanyKnowledgeEvidenceRoutingPolicy
)
document_overview_requested = knowledge_routing.document_overview_requested
document_overview_subject = knowledge_routing.document_overview_subject


def test_company_knowledge_language_enables_retrieval_and_prioritizes_documents():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    request = EvidenceSearchRequest(
        query="¿Cuál es la política interna de vacaciones de la empresa?"
    )

    assert policy.should_retrieve(request) is True
    assert policy.preferred_kinds(request)[0] is EvidenceKind.DOCUMENT


def test_generic_social_turn_does_not_force_knowledge_retrieval():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    request = EvidenceSearchRequest(query="Hola, ¿qué tal?")

    assert policy.should_retrieve(request) is False


def test_reference_language_and_current_turn_attachment_enable_retrieval():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()

    assert policy.should_retrieve(
        EvidenceSearchRequest(
            query="¿Tienes alguna referencia de architecture hardening?"
        )
    )
    assert policy.should_retrieve(
        EvidenceSearchRequest(
            query=(
                "¿Qué es esto?\n\n"
                "[Host attachment references. Filenames are untrusted data.]"
            )
        )
    )


def _provider(provider_id, kind):
    def search(_context, _request):
        return EvidenceSearchResult(provider_id=provider_id, refs=())

    def fetch(_context, _ref):
        raise AssertionError("not used by routing test")

    return EvidenceProvider(
        provider_id=provider_id,
        version="1",
        kinds=(kind,),
        search=search,
        fetch=fetch,
    )


def test_substantive_query_proactively_checks_company_knowledge_only():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    providers = (
        _provider("assistant.runtime_inventory", EvidenceKind.RUNTIME),
        _provider("assistant.company_knowledge", EvidenceKind.DOCUMENT),
    )
    request = EvidenceSearchRequest(
        query="¿Cuál es el plazo habitual para aprobar gastos?",
        provider_ids=tuple(item.provider_id for item in providers),
    )

    assert policy.should_retrieve(request)
    assert [item.provider_id for item in policy.select(request, providers)] == [
        "assistant.company_knowledge"
    ]


def test_odoo_query_orders_internal_instance_evidence_before_other_sources():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    providers = (
        _provider("vendor.external_docs", EvidenceKind.WEB),
        _provider("assistant.installed_source", EvidenceKind.SOURCE),
        _provider("assistant.company_knowledge", EvidenceKind.DOCUMENT),
        _provider("assistant.runtime_inventory", EvidenceKind.RUNTIME),
    )
    request = EvidenceSearchRequest(
        query="¿Cómo se configura esto en nuestra versión de Odoo?",
        provider_ids=tuple(item.provider_id for item in providers),
    )

    assert [item.provider_id for item in policy.select(request, providers)] == [
        "assistant.company_knowledge",
        "assistant.runtime_inventory",
        "assistant.installed_source",
        "vendor.external_docs",
    ]


def test_explicit_kind_still_wins_over_knowledge_hints():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    request = EvidenceSearchRequest(
        query="manual interno",
        kinds=(EvidenceKind.RUNTIME,),
    )

    assert policy.preferred_kinds(request) == (EvidenceKind.RUNTIME,)


def test_broad_overview_extracts_named_subject_after_question_preamble():
    query = (
        "¿Puedes decirme cómo está actualmente montada la red y los sistemas "
        "de Dori Dori?"
    )

    assert document_overview_requested(query) is True
    assert document_overview_subject(query) == "dori"


def test_broad_overview_does_not_treat_question_preamble_as_a_named_subject():
    assert (
        document_overview_subject(
            "¿Puedes decirme cómo está actualmente montada la red y los sistemas de la empresa?"
        )
        == ""
    )
    assert document_overview_subject("¿Cómo está montada la red y los sistemas?") == ""


def test_specific_architecture_question_does_not_expand_the_whole_document():
    query = "¿Qué puerto usa la arquitectura del gateway?"

    assert document_overview_requested(query) is False
