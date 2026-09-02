"""P9 Evidence routing extension for company-document questions without a rigid intent router."""

from __future__ import annotations

from .evidence import EvidenceKind, EvidenceRoutingPolicy, EvidenceSearchRequest

_KNOWLEDGE_HINTS = (
    "knowledge",
    "document",
    "documento",
    "documentación",
    "documentacion",
    "manual",
    "policy",
    "política",
    "politica",
    "procedimiento",
    "procedure",
    "empresa",
    "company",
    "interno",
    "interna",
    "internal",
    "guía",
    "guia",
    "handbook",
)


class CompanyKnowledgeEvidenceRoutingPolicy(EvidenceRoutingPolicy):
    """Prefer DOCUMENT Evidence when language points at governed company knowledge."""

    def should_retrieve(self, request: EvidenceSearchRequest) -> bool:
        if super().should_retrieve(request):
            return True
        query = request.query.casefold()
        return any(token in query for token in _KNOWLEDGE_HINTS)

    def preferred_kinds(self, request: EvidenceSearchRequest) -> tuple[EvidenceKind, ...]:
        if request.kinds:
            return request.kinds
        query = request.query.casefold()
        if any(token in query for token in _KNOWLEDGE_HINTS):
            return (
                EvidenceKind.DOCUMENT,
                EvidenceKind.BUSINESS_RECORD,
                EvidenceKind.RUNTIME,
                EvidenceKind.CONFIGURATION,
            )
        return super().preferred_kinds(request)


__all__ = ["CompanyKnowledgeEvidenceRoutingPolicy"]
