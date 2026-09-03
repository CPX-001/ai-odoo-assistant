"""P9 Evidence routing extension for company-document questions without a rigid intent router."""

from __future__ import annotations

import re
import unicodedata
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
_OVERVIEW_SUBJECT_SEPARATOR_RE = re.compile(r"\b(?:about|de|del|of|sobre)\b")
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
_OVERVIEW_PHRASES = (
    "como esta montad",
    "como se organiza",
    "como esta organizad",
    "vision general",
    "panorama completo",
    "full overview",
    "complete overview",
    "how is it set up",
    "how is this set up",
)
_OVERVIEW_NOUNS = frozenset(
    {"arquitectura", "infraestructura", "topologia", "architecture", "infrastructure"}
)
_OVERVIEW_SETUP_WORDS = frozenset(
    {"montado", "montada", "organizado", "organizada", "desplegado", "desplegada", "setup"}
)
_OVERVIEW_DOMAIN_WORDS = frozenset(
    {"red", "redes", "sistema", "sistemas", "entorno", "plataforma", "network", "systems"}
)
_OVERVIEW_SCOPE_WORDS = frozenset(
    {"completa", "completo", "general", "global", "overview", "panorama", "resumen", "toda", "todo"}
)
_OVERVIEW_SUBJECT_NOISE = frozenset(
    {
        "actual",
        "actualmente",
        "como",
        "current",
        "currently",
        "cual",
        "cuales",
        "de",
        "decir",
        "decirme",
        "del",
        "el",
        "en",
        "empresa",
        "esta",
        "este",
        "general",
        "give",
        "how",
        "is",
        "it",
        "la",
        "las",
        "los",
        "me",
        "montada",
        "montado",
        "mostrar",
        "muestrame",
        "organizada",
        "organizado",
        "overview",
        "please",
        "podrias",
        "puede",
        "puedes",
        "que",
        "se",
        "tell",
        "the",
        "una",
        "un",
        "vision",
        "y",
    }
).union(
    _OVERVIEW_NOUNS,
    _OVERVIEW_SETUP_WORDS,
    _OVERVIEW_DOMAIN_WORDS,
    _OVERVIEW_SCOPE_WORDS,
)


def document_overview_subject(query: object) -> str:
    """Extract the named subject from a broad overview question when one exists."""

    if not isinstance(query, str) or not query.strip():
        return ""
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", query.casefold())
        if not unicodedata.combining(character)
    )
    segments = _OVERVIEW_SUBJECT_SEPARATOR_RE.split(normalized)
    if len(segments) > 1:
        # A named subject belongs after the final preposition. If that tail is only
        # generic wording (for example, "de la empresa"), fall back to the original
        # query instead of treating words from the question preamble as a name.
        segments = segments[-1:]
    for segment in reversed(segments):
        subject_tokens = tuple(
            dict.fromkeys(
                token
                for token in _QUERY_TOKEN_RE.findall(segment)
                if token not in _OVERVIEW_SUBJECT_NOISE
            )
        )
        if subject_tokens:
            return " ".join(subject_tokens)
    return ""


def document_overview_requested(query: object) -> bool:
    """Identify broad document-coverage questions without changing capability routing."""

    if not isinstance(query, str) or not query.strip():
        return False
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", query.casefold())
        if not unicodedata.combining(character)
    )
    if any(phrase in normalized for phrase in _OVERVIEW_PHRASES):
        return True
    tokens = set(_QUERY_TOKEN_RE.findall(normalized))
    if {"red", "sistemas"}.issubset(tokens) or {"network", "systems"}.issubset(tokens):
        return True
    return bool(
        (
            tokens.intersection(_OVERVIEW_SETUP_WORDS)
            and tokens.intersection(_OVERVIEW_DOMAIN_WORDS | _OVERVIEW_NOUNS)
        )
        or (
            tokens.intersection(_OVERVIEW_NOUNS)
            and tokens.intersection(_OVERVIEW_SCOPE_WORDS)
        )
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


__all__ = [
    "CompanyKnowledgeEvidenceRoutingPolicy",
    "document_overview_requested",
    "document_overview_subject",
]
