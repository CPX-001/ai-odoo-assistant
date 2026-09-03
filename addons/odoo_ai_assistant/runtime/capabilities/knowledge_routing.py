"""P9 Evidence routing extension for company-document questions without a rigid intent router."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .evidence import (
    EvidenceKind,
    EvidenceProvider,
    EvidenceRoutingPolicy,
    EvidenceSearchRequest,
)

_ATTACHMENT_MARKER = "[host attachment references."
_ATTACHMENT_PROVIDER_ID = "assistant.turn_attachment"
_COMPANY_KNOWLEDGE_PROVIDER_ID = "assistant.company_knowledge"
_QUERY_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ_]{2,}")
_SOCIAL_ONLY_TOKENS = frozenset(
    {
        "buenas",
        "buenos",
        "día",
        "dias",
        "días",
        "gracias",
        "hello",
        "hey",
        "hola",
        "tal",
        "thanks",
        "qué",
    }
)
_PROVIDER_PRIORITY = {
    _ATTACHMENT_PROVIDER_ID: 0,
    _COMPANY_KNOWLEDGE_PROVIDER_ID: 1,
    "assistant.runtime_inventory": 2,
    "assistant.installed_source": 3,
    "assistant.odoo_log": 4,
}

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
    "reference",
    "references",
    "referencia",
    "referencias",
    "fuente",
    "fuentes",
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
        if _ATTACHMENT_MARKER in query or any(
            token in query for token in _KNOWLEDGE_HINTS
        ):
            return True
        tokens = tuple(_QUERY_TOKEN_RE.findall(query))
        return bool(tokens) and not set(tokens).issubset(_SOCIAL_ONLY_TOKENS)

    def preferred_kinds(
        self, request: EvidenceSearchRequest
    ) -> tuple[EvidenceKind, ...]:
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
        if self.should_retrieve(request) and not super().should_retrieve(request):
            return (
                EvidenceKind.DOCUMENT,
                EvidenceKind.BUSINESS_RECORD,
                EvidenceKind.RUNTIME,
                EvidenceKind.SCHEMA,
            )
        return super().preferred_kinds(request)

    def select(
        self,
        request: EvidenceSearchRequest,
        providers: Iterable[EvidenceProvider],
    ) -> tuple[EvidenceProvider, ...]:
        selected = super().select(request, providers)
        query = request.query.casefold()
        query_probe = EvidenceSearchRequest(query=request.query)
        explicit_internal_route = (
            EvidenceRoutingPolicy.should_retrieve(self, query_probe)
            or _ATTACHMENT_MARKER in query
            or any(token in query for token in _KNOWLEDGE_HINTS)
        )
        if not explicit_internal_route:
            return tuple(
                item
                for item in selected
                if item.provider_id == _COMPANY_KNOWLEDGE_PROVIDER_ID
            )
        return tuple(
            sorted(
                selected,
                key=lambda item: (
                    _PROVIDER_PRIORITY.get(item.provider_id, 100),
                    item.provider_id,
                ),
            )
        )


__all__ = ["CompanyKnowledgeEvidenceRoutingPolicy"]
