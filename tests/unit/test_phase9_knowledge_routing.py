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


evidence = importlib.import_module("addons.odoo_ai_assistant.runtime.capabilities.evidence")
knowledge_routing = importlib.import_module(
    "addons.odoo_ai_assistant.runtime.capabilities.knowledge_routing"
)

EvidenceKind = evidence.EvidenceKind
EvidenceSearchRequest = evidence.EvidenceSearchRequest
CompanyKnowledgeEvidenceRoutingPolicy = (
    knowledge_routing.CompanyKnowledgeEvidenceRoutingPolicy
)


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


def test_explicit_kind_still_wins_over_knowledge_hints():
    policy = CompanyKnowledgeEvidenceRoutingPolicy()
    request = EvidenceSearchRequest(
        query="manual interno",
        kinds=(EvidenceKind.RUNTIME,),
    )

    assert policy.preferred_kinds(request) == (EvidenceKind.RUNTIME,)
