"""Bounded Evidence for files explicitly attached to the current Assistant turn."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from odoo.addons.odoo_ai_assistant.models.knowledge import (
    _chunk_text,
    _decode_binary,
    _extract_document_text,
)

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

PROVIDER_ID = "assistant.turn_attachment"
SOURCE_ID = "assistant.turn"
_MAX_RESULTS = 16
_MAX_EXCERPT = 8 * 1024
_QUERY_TERM_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ_]{2,}")
_HOST_DESCRIPTOR = "\n\n[Host attachment references."
_STOP_WORDS = frozenset(
    {
        "archivo",
        "attached",
        "attachment",
        "como",
        "cómo",
        "cual",
        "cuál",
        "del",
        "document",
        "documento",
        "esto",
        "file",
        "las",
        "los",
        "que",
        "qué",
        "the",
        "this",
        "una",
    }
)


def _turn(context: CapabilityContext):
    try:
        return context.env["odoo.ai.turn"].search(
            [
                ("turn_uuid", "=", context.turn_id),
                ("user_id", "=", context.env.uid),
            ],
            limit=1,
        )
    except Exception as error:
        raise CapabilityError("turn_attachment_access_denied") from error


def _attachments(context: CapabilityContext):
    turn = _turn(context)
    if not turn:
        return context.env["odoo.ai.knowledge.attachment"].browse()
    return turn.knowledge_attachment_ids.filtered(
        lambda item: item.user_id.id == context.env.uid
    )


def _guard(context: CapabilityContext) -> bool:
    try:
        return bool(context.env.user._is_internal() and _attachments(context))
    except Exception:  # noqa: BLE001 - optional Evidence availability fails closed
        return False


def _attachment_text(attachment) -> str:
    if attachment.extracted_text:
        return attachment.extracted_text
    raw = _decode_binary(attachment.data)
    return _extract_document_text(raw, attachment.filename, attachment.mimetype)


def _human_query(value: str) -> str:
    return value.split(_HOST_DESCRIPTOR, 1)[0].strip()


def _terms(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item
            for item in _QUERY_TERM_RE.findall(_human_query(value).casefold())
            if item not in _STOP_WORDS
        )
    )[:24]


def _search(context: CapabilityContext, request: EvidenceSearchRequest):
    if request.kinds and EvidenceKind.DOCUMENT not in request.kinds:
        return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
    terms = _terms(request.query)
    ranked = []
    fallback = []
    for attachment in _attachments(context):
        chunks = _chunk_text(_attachment_text(attachment))
        filename = attachment.filename.casefold()
        for sequence, chunk in enumerate(chunks, start=1):
            content = chunk["content"]
            folded = content.casefold()
            matches = sum(term in folded for term in terms)
            name_matches = sum(term in filename for term in terms)
            score = float(name_matches * 100 + matches * 10)
            ref = _ref(
                context,
                attachment,
                sequence=sequence,
                chunk=chunk,
                score=score,
            )
            if score:
                ranked.append((score, sequence, ref))
            elif sequence <= 2:
                fallback.append((attachment.id, sequence, ref))
    selected = (
        [item[2] for item in sorted(ranked, key=lambda item: (-item[0], item[1]))]
        if ranked
        else [item[2] for item in sorted(fallback, key=lambda item: (item[1], item[0]))]
    )
    limit = min(request.max_results, _MAX_RESULTS)
    return EvidenceSearchResult(
        provider_id=PROVIDER_ID,
        refs=tuple(selected[:limit]),
        truncated=len(selected) > limit,
    )


def _fetch(context: CapabilityContext, requested: EvidenceRef) -> EvidenceItem:
    if (
        requested.provider_id != PROVIDER_ID
        or requested.kind is not EvidenceKind.DOCUMENT
    ):
        raise CapabilityError("evidence_provider_mismatch")
    if not requested.access_scope.allows(context):
        raise CapabilityError("evidence_access_denied")
    try:
        token, sequence_text = requested.locator.key.split("/", 1)
        sequence = int(sequence_text)
    except (TypeError, ValueError):
        raise CapabilityError("evidence_locator_invalid") from None
    attachment = _attachments(context).filtered(lambda item: item.token == token)[:1]
    if not attachment:
        raise CapabilityError("evidence_access_denied")
    chunks = _chunk_text(_attachment_text(attachment))
    if sequence <= 0 or sequence > len(chunks):
        raise CapabilityError("evidence_locator_invalid")
    chunk = chunks[sequence - 1]
    current = _ref(
        context,
        attachment,
        sequence=sequence,
        chunk=chunk,
        score=requested.score or 0.0,
    )
    freshness = (
        EvidenceFreshness.CURRENT
        if current.fingerprint == requested.fingerprint
        else EvidenceFreshness.STALE
    )
    current = current.with_freshness(freshness)
    return EvidenceItem(
        ref=current,
        excerpt=chunk["content"][:_MAX_EXCERPT],
        data={
            "filename": attachment.filename,
            "mimetype": attachment.mimetype,
            "size": attachment.file_size,
            "section": sequence,
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
            "temporary": True,
            "trust_boundary": "untrusted_user_attachment",
        },
    )


def _ref(context, attachment, *, sequence: int, chunk, score: float) -> EvidenceRef:
    fingerprint = hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest()
    return EvidenceRef(
        evidence_id=f"attachment:{attachment.token}:{sequence}",
        kind=EvidenceKind.DOCUMENT,
        provider_id=PROVIDER_ID,
        locator=EvidenceLocator(
            provider_id=PROVIDER_ID,
            source_id=SOURCE_ID,
            key=f"{attachment.token}/{sequence}",
            parameters={"attachment_fingerprint": attachment.fingerprint},
        ),
        title=attachment.filename,
        provenance=f"File attached by the current user: {attachment.filename}",
        fingerprint=fingerprint,
        captured_at=datetime.now(UTC),
        freshness=EvidenceFreshness.CURRENT,
        trust=EvidenceTrust.USER_CONTENT,
        access_scope=EvidenceAccessScope.bind(context),
        citation={
            "source_type": "turn_attachment",
            "filename": attachment.filename,
            "section": sequence,
            "char_start": chunk["char_start"],
            "char_end": chunk["char_end"],
        },
        conflict_group=f"attachment:{attachment.token[:20]}:{sequence}",
        score=max(0.0, score),
        metadata={
            "mimetype": attachment.mimetype,
            "size": attachment.file_size,
            "temporary": True,
        },
    )


def build_turn_attachment_evidence_provider() -> EvidenceProvider:
    return EvidenceProvider(
        provider_id=PROVIDER_ID,
        version="1",
        kinds=(EvidenceKind.DOCUMENT,),
        search=_search,
        fetch=_fetch,
        optional=True,
        max_results=_MAX_RESULTS,
        max_excerpt_bytes=_MAX_EXCERPT,
        max_total_bytes=64 * 1024,
        timeout_seconds=8,
        guard=_guard,
        metadata={
            "source": "current_turn_attachment",
            "content_trust": "untrusted_user_content",
            "temporary": True,
        },
    )


__all__ = ["PROVIDER_ID", "build_turn_attachment_evidence_provider"]
