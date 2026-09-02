"""Company Knowledge EvidenceProvider backed by Odoo ACLs and PostgreSQL lexical search."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .contracts import CapabilityContext, CapabilityError
from .evidence import (
    EvidenceAccessScope,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidenceProvider,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    EvidenceTrust,
)

PROVIDER_ID = "assistant.company_knowledge"
SOURCE_ID = "company.knowledge"
_MAX_EXCERPT = 8 * 1024


def _guard(context: CapabilityContext) -> bool:
    try:
        return bool(context.env.user._is_internal())
    except Exception:
        return False


def _search(context: CapabilityContext, request: EvidenceSearchRequest):
    if request.kinds and EvidenceKind.DOCUMENT not in request.kinds:
        return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
    limit = min(request.max_results, 12)
    try:
        ranked = context.env["odoo.ai.knowledge.source"].lexical_search(
            request.query,
            limit=limit,
        )
    except Exception as error:
        raise CapabilityError("knowledge_search_failed") from error
    refs = tuple(_ref_for_chunk(context, chunk, score) for chunk, score in ranked)
    return EvidenceSearchResult(
        provider_id=PROVIDER_ID,
        refs=refs,
        truncated=len(refs) >= limit,
    )


def _fetch(context: CapabilityContext, requested: EvidenceRef) -> EvidenceItem:
    if requested.provider_id != PROVIDER_ID or requested.kind is not EvidenceKind.DOCUMENT:
        raise CapabilityError("evidence_provider_mismatch")
    if not requested.access_scope.allows(context):
        raise CapabilityError("evidence_access_denied")
    source_uuid, sequence = _locator_parts(requested)
    try:
        source = context.env["odoo.ai.knowledge.source"].search(
            [("source_uuid", "=", source_uuid)],
            limit=1,
        )
    except Exception as error:
        raise CapabilityError("evidence_access_denied") from error
    if not source:
        raise CapabilityError("evidence_access_denied")

    requested_version = requested.locator.parameters.get("version")
    if type(requested_version) is not int:
        raise CapabilityError("evidence_locator_invalid")
    if not source.enabled:
        return EvidenceItem(
            ref=replace(requested, freshness=EvidenceFreshness.REVOKED),
            excerpt="",
            data={"state": "disabled", "source_uuid": source.source_uuid},
        )
    if source.state != "active" or source.version != requested_version:
        return EvidenceItem(
            ref=replace(requested, freshness=EvidenceFreshness.STALE),
            excerpt="",
            data={
                "state": source.state,
                "source_uuid": source.source_uuid,
                "requested_version": requested_version,
                "current_version": source.version,
            },
        )
    chunk = context.env["odoo.ai.knowledge.chunk"].search(
        [
            ("source_id", "=", source.id),
            ("source_version", "=", source.version),
            ("sequence", "=", sequence),
        ],
        limit=1,
    )
    if not chunk or chunk.content_fingerprint != requested.fingerprint:
        return EvidenceItem(
            ref=replace(requested, freshness=EvidenceFreshness.STALE),
            excerpt="",
            data={
                "state": "changed",
                "source_uuid": source.source_uuid,
                "current_version": source.version,
            },
        )
    current = _ref_for_chunk(context, chunk, requested.score or 0.0)
    return EvidenceItem(
        ref=current,
        excerpt=chunk.content[:_MAX_EXCERPT],
        data={
            "source_uuid": source.source_uuid,
            "source_name": source.name,
            "source_version": source.version,
            "chunk": chunk.sequence,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "trust_boundary": "untrusted_company_content",
        },
    )


def _ref_for_chunk(context: CapabilityContext, chunk, score: float) -> EvidenceRef:
    source = chunk.source_id
    version = int(chunk.source_version)
    sequence = int(chunk.sequence)
    return EvidenceRef(
        evidence_id=f"knowledge:{source.source_uuid[:24]}:{version}:{sequence}",
        kind=EvidenceKind.DOCUMENT,
        provider_id=PROVIDER_ID,
        locator=EvidenceLocator(
            provider_id=PROVIDER_ID,
            source_id=SOURCE_ID,
            key=f"{source.source_uuid}/{sequence}",
            parameters={"version": version},
        ),
        title=source.name,
        provenance=f"Company Knowledge source {source.name}",
        fingerprint=chunk.content_fingerprint,
        captured_at=datetime.now(UTC),
        freshness=EvidenceFreshness.CURRENT,
        trust=EvidenceTrust.USER_CONTENT,
        access_scope=EvidenceAccessScope.bind(context),
        citation={
            "source_type": "company_knowledge",
            "source_uuid": source.source_uuid,
            "source_name": source.name,
            "version": version,
            "chunk": sequence,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
        },
        conflict_group=f"knowledge:{source.source_uuid[:24]}:{sequence}",
        score=max(0.0, float(score)),
        metadata={
            "access_mode": source.access_mode,
            "company_id": source.company_id.id,
            "indexed_fingerprint": source.indexed_fingerprint,
        },
    )


def _locator_parts(ref: EvidenceRef) -> tuple[str, int]:
    try:
        source_uuid, sequence_text = ref.locator.key.split("/", 1)
        sequence = int(sequence_text)
    except (TypeError, ValueError):
        raise CapabilityError("evidence_locator_invalid") from None
    if len(source_uuid) != 32 or sequence <= 0:
        raise CapabilityError("evidence_locator_invalid")
    return source_uuid, sequence


def build_company_knowledge_evidence_provider() -> EvidenceProvider:
    return EvidenceProvider(
        provider_id=PROVIDER_ID,
        version="1",
        kinds=(EvidenceKind.DOCUMENT,),
        search=_search,
        fetch=_fetch,
        optional=True,
        max_results=12,
        max_excerpt_bytes=_MAX_EXCERPT,
        max_total_bytes=64 * 1024,
        timeout_seconds=8,
        guard=_guard,
        metadata={
            "source": "odoo_company_knowledge",
            "retrieval": "postgresql_fts_lexical_first",
            "content_trust": "untrusted_data",
        },
    )


__all__ = ["PROVIDER_ID", "build_company_knowledge_evidence_provider"]
