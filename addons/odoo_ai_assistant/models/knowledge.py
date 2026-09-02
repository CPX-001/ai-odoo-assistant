"""Odoo-native company Knowledge sources, bounded ingestion and lexical retrieval."""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import timedelta
from uuid import uuid4

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_SOURCE_TEXT_CHARS = 8 * 1024 * 1024
_MAX_CHUNK_CHARS = 6_000
_MAX_CHUNKS = 2_048
_MAX_SEARCH_RESULTS = 20
_MAX_FILENAME = 255
_MAX_ATTACHMENT_COUNT_PER_TURN = 8
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_SUPPORTED_MIMETYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "text/csv",
        "text/markdown",
        "text/plain",
        "text/x-rst",
        "text/xml",
    }
)
_SUPPORTED_EXTENSIONS = frozenset(
    {".csv", ".json", ".md", ".markdown", ".rst", ".txt", ".xml"}
)
_SOURCE_INTERNAL_FIELDS = frozenset(
    {
        "source_uuid",
        "owner_user_id",
        "company_id",
        "conversation_id",
        "state",
        "file_size",
        "content_fingerprint",
        "indexed_fingerprint",
        "version",
        "chunk_count",
        "indexed_at",
        "error_code",
    }
)
_ATTACHMENT_INTERNAL_FIELDS = frozenset(
    {
        "token",
        "user_id",
        "company_id",
        "turn_id",
        "conversation_id",
        "file_size",
        "fingerprint",
        "expires_at",
        "consumed_at",
        "knowledge_source_id",
    }
)


class KnowledgeProcessingError(ValidationError):
    """Bounded ingestion failure with a stable public error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssistantKnowledgeSource(models.Model):
    _name = "odoo.ai.knowledge.source"
    _description = "Odoo AI Assistant Knowledge Source"
    _order = "write_date desc, id desc"

    source_uuid = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: uuid4().hex,
    )
    name = fields.Char(required=True, size=160)
    owner_user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    conversation_id = fields.Many2one(
        "odoo.ai.conversation",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    access_mode = fields.Selection(
        [("private", "Private"), ("company", "Company")],
        required=True,
        default="company",
        index=True,
    )
    enabled = fields.Boolean(required=True, default=True, index=True)
    state = fields.Selection(
        [
            ("uploaded", "Uploaded"),
            ("processing", "Processing"),
            ("indexed", "Indexed"),
            ("active", "Active"),
            ("error", "Error"),
        ],
        required=True,
        readonly=True,
        default="uploaded",
        index=True,
    )
    filename = fields.Char(required=True, size=_MAX_FILENAME)
    mimetype = fields.Char(required=True, size=120)
    data = fields.Binary(required=True, attachment=True)
    file_size = fields.Integer(readonly=True)
    content_fingerprint = fields.Char(readonly=True, index=True, size=64)
    indexed_fingerprint = fields.Char(readonly=True, index=True, size=64)
    version = fields.Integer(required=True, readonly=True, default=0)
    chunk_count = fields.Integer(required=True, readonly=True, default=0)
    indexed_at = fields.Datetime(readonly=True)
    error_code = fields.Char(readonly=True, size=128)
    chunk_ids = fields.One2many(
        "odoo.ai.knowledge.chunk",
        "source_id",
        string="Indexed chunks",
    )

    _sql_constraints = [
        (
            "knowledge_source_uuid_unique",
            "unique(source_uuid)",
            "Knowledge source id must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            values = dict(incoming)
            if not self.env.su:
                for key in _SOURCE_INTERNAL_FIELDS:
                    values.pop(key, None)
                values["owner_user_id"] = self.env.uid
                values["company_id"] = self.env.company.id
                conversation_id = incoming.get("conversation_id")
                if conversation_id:
                    conversation = self.env["odoo.ai.conversation"].browse(
                        int(conversation_id)
                    ).exists()
                    if (
                        not conversation
                        or conversation.user_id.id != self.env.uid
                        or conversation.company_id.id != self.env.company.id
                    ):
                        raise AccessError("Knowledge conversation is not accessible")
                    values["conversation_id"] = conversation.id
            filename = _filename(values.get("filename"))
            mimetype = _mimetype(values.get("mimetype"), filename)
            raw = _decode_binary(values.get("data"))
            _validate_supported_document(filename, mimetype)
            values["filename"] = filename
            values["mimetype"] = mimetype
            values["file_size"] = len(raw)
            values["content_fingerprint"] = hashlib.sha256(raw).hexdigest()
            values.setdefault("state", "uploaded")
            values.setdefault("version", 0)
            values.setdefault("chunk_count", 0)
            if not values.get("name"):
                values["name"] = filename[:160]
            prepared.append(values)
        records = super().create(prepared)
        records._trigger_processing_cron()
        return records

    def write(self, vals):
        requested = dict(vals)
        if not self.env.su and set(requested) & _SOURCE_INTERNAL_FIELDS:
            raise AccessError("Knowledge lifecycle fields are host-owned")
        content_change = any(key in requested for key in ("data", "filename", "mimetype"))
        prepared = dict(requested)
        if content_change:
            if len(self) != 1:
                raise ValidationError("Update Knowledge source files one record at a time")
            filename = _filename(prepared.get("filename", self.filename))
            mimetype = _mimetype(prepared.get("mimetype", self.mimetype), filename)
            raw = _decode_binary(prepared.get("data", self.data))
            _validate_supported_document(filename, mimetype)
            prepared.update(
                {
                    "filename": filename,
                    "mimetype": mimetype,
                    "file_size": len(raw),
                    "content_fingerprint": hashlib.sha256(raw).hexdigest(),
                    "state": "uploaded",
                    "error_code": False,
                }
            )
        result = super().write(prepared)
        if content_change:
            self._trigger_processing_cron()
        return result

    def action_queue_processing(self):
        self.check_access("write")
        for source in self:
            source.with_user(SUPERUSER_ID).write(
                {"state": "uploaded", "error_code": False}
            )
        self._trigger_processing_cron()
        return True

    def action_reindex(self):
        return self.action_queue_processing()

    def action_process_now(self):
        self.check_access("write")
        for source in self:
            source._process_one()
        return True

    def action_activate(self):
        self.check_access("write")
        for source in self:
            if source.indexed_fingerprint and source.chunk_count:
                source.with_user(SUPERUSER_ID).write(
                    {"enabled": True, "state": "active", "error_code": False}
                )
        return True

    def action_disable(self):
        self.check_access("write")
        for source in self:
            state = "indexed" if source.indexed_fingerprint else source.state
            source.with_user(SUPERUSER_ID).write(
                {"enabled": False, "state": state}
            )
        return True

    @api.model
    def _cron_process_pending(self):
        sources = self.with_user(SUPERUSER_ID).search(
            [("state", "=", "uploaded")],
            order="id",
            limit=2,
        )
        for source in sources:
            source._process_one()
        self.env["odoo.ai.knowledge.attachment"]._cron_cleanup_expired()

    def _process_one(self):
        self.ensure_one()
        self.check_access("write")
        system_source = self.with_user(SUPERUSER_ID)
        system_source.write({"state": "processing", "error_code": False})
        try:
            raw = _decode_binary(self.data)
            _validate_supported_document(self.filename, self.mimetype)
            fingerprint = hashlib.sha256(raw).hexdigest()
            text = _extract_text(raw)
            chunks = _chunk_text(text)
            if not chunks:
                raise KnowledgeProcessingError("knowledge_empty_document")
            version = self.version + 1
            system_source.chunk_ids.unlink()
            rows = []
            for sequence, chunk in enumerate(chunks, start=1):
                rows.append(
                    {
                        "source_id": self.id,
                        "sequence": sequence,
                        "source_version": version,
                        "content": chunk["content"],
                        "char_start": chunk["char_start"],
                        "char_end": chunk["char_end"],
                        "content_fingerprint": hashlib.sha256(
                            chunk["content"].encode("utf-8")
                        ).hexdigest(),
                    }
                )
            self.env["odoo.ai.knowledge.chunk"].with_user(SUPERUSER_ID).create(rows)
            now = fields.Datetime.now()
            final_state = "active" if self.enabled else "indexed"
            system_source.write(
                {
                    "file_size": len(raw),
                    "content_fingerprint": fingerprint,
                    "indexed_fingerprint": fingerprint,
                    "version": version,
                    "chunk_count": len(rows),
                    "indexed_at": now,
                    "state": final_state,
                    "error_code": False,
                }
            )
        except KnowledgeProcessingError as error:
            system_source.write(
                {"state": "error", "error_code": error.code[:128]}
            )
        except Exception:
            system_source.write(
                {"state": "error", "error_code": "knowledge_processing_failed"}
            )
        return self.state

    @api.model
    def lexical_search(self, query, *, limit=8):
        """Return ACL-filtered active chunks using PostgreSQL FTS plus exact fallback."""

        if not isinstance(query, str) or not query.strip():
            raise ValidationError("Knowledge query is required")
        query = " ".join(query.split())[:4_096]
        if not 1 <= int(limit) <= _MAX_SEARCH_RESULTS:
            raise ValidationError("Invalid Knowledge result limit")
        source_ids = self.search(
            [("enabled", "=", True), ("state", "=", "active")]
        ).ids
        if not source_ids:
            return []
        exact = f"%{query[:1_000]}%"
        self.env.cr.execute(
            """
            SELECT c.id,
                   CASE WHEN c.content ILIKE %s THEN 1 ELSE 0 END AS exact_match,
                   ts_rank_cd(
                       to_tsvector('simple', COALESCE(c.content, '')),
                       plainto_tsquery('simple', %s)
                   ) AS rank
              FROM odoo_ai_knowledge_chunk AS c
             WHERE c.source_id = ANY(%s)
               AND (
                    c.content ILIKE %s
                    OR to_tsvector('simple', COALESCE(c.content, ''))
                       @@ plainto_tsquery('simple', %s)
               )
             ORDER BY exact_match DESC, rank DESC, c.source_id, c.sequence
             LIMIT %s
            """,
            (exact, query, source_ids, exact, query, int(limit)),
        )
        ranked = self.env.cr.fetchall()
        if not ranked:
            return []
        rank_by_id = {row[0]: float(row[2] or 0.0) + float(row[1] or 0.0) for row in ranked}
        chunks = self.env["odoo.ai.knowledge.chunk"].search(
            [("id", "in", list(rank_by_id))]
        )
        by_id = {chunk.id: chunk for chunk in chunks}
        return [
            (by_id[chunk_id], rank_by_id[chunk_id])
            for chunk_id, _exact, _rank in ranked
            if chunk_id in by_id
        ]

    def _trigger_processing_cron(self):
        cron = self.env.ref(
            "odoo_ai_assistant.ir_cron_assistant_knowledge_ingest",
            raise_if_not_found=False,
        )
        if cron:
            cron._trigger()


class AssistantKnowledgeChunk(models.Model):
    _name = "odoo.ai.knowledge.chunk"
    _description = "Odoo AI Assistant Knowledge Chunk"
    _order = "source_id, sequence, id"

    source_id = fields.Many2one(
        "odoo.ai.knowledge.source",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(required=True, index=True)
    source_version = fields.Integer(required=True, index=True)
    content = fields.Text(required=True)
    char_start = fields.Integer(required=True)
    char_end = fields.Integer(required=True)
    content_fingerprint = fields.Char(required=True, index=True, size=64)

    _sql_constraints = [
        (
            "knowledge_chunk_source_sequence_unique",
            "unique(source_id, source_version, sequence)",
            "Knowledge chunk sequence must be unique per source version.",
        ),
    ]


class AssistantKnowledgeAttachment(models.Model):
    """Short-lived chat attachment; never becomes Knowledge until an authorized capability does it."""

    _name = "odoo.ai.knowledge.attachment"
    _description = "Odoo AI Assistant Pending Knowledge Attachment"
    _order = "id desc"

    token = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: uuid4().hex,
        size=32,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    turn_id = fields.Many2one(
        "odoo.ai.turn",
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    conversation_id = fields.Many2one(
        "odoo.ai.conversation",
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    filename = fields.Char(required=True, readonly=True, size=_MAX_FILENAME)
    mimetype = fields.Char(required=True, readonly=True, size=120)
    data = fields.Binary(required=True, readonly=True, attachment=True)
    file_size = fields.Integer(required=True, readonly=True)
    fingerprint = fields.Char(required=True, readonly=True, index=True, size=64)
    expires_at = fields.Datetime(required=True, readonly=True, index=True)
    consumed_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "knowledge_attachment_token_unique",
            "unique(token)",
            "Knowledge attachment token must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            values = dict(incoming)
            if not self.env.su:
                for key in _ATTACHMENT_INTERNAL_FIELDS:
                    values.pop(key, None)
                values["user_id"] = self.env.uid
                values["company_id"] = self.env.company.id
            filename = _filename(values.get("filename"))
            mimetype = _mimetype(values.get("mimetype"), filename)
            raw = _decode_binary(values.get("data"))
            _validate_supported_document(filename, mimetype)
            values["filename"] = filename
            values["mimetype"] = mimetype
            values["file_size"] = len(raw)
            values["fingerprint"] = hashlib.sha256(raw).hexdigest()
            values.setdefault("expires_at", fields.Datetime.now() + timedelta(hours=24))
            prepared.append(values)
        return super().create(prepared)

    def write(self, vals):
        if not self.env.su and vals:
            raise AccessError("Pending Knowledge attachments are immutable")
        return super().write(vals)

    @api.model
    def create_upload(self, *, filename, mimetype, data):
        if not self.env.user._is_internal():
            raise AccessError("Assistant attachments require an internal user")
        return self.create(
            {
                "filename": filename,
                "mimetype": mimetype,
                "data": data,
            }
        )

    @api.model
    def owned_by_tokens(self, tokens):
        normalized = []
        for token in tokens:
            if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
                raise ValidationError("Invalid Assistant attachment token")
            if token not in normalized:
                normalized.append(token)
        if len(normalized) > _MAX_ATTACHMENT_COUNT_PER_TURN:
            raise ValidationError("Too many Assistant attachments")
        records = self.search(
            [("token", "in", normalized), ("user_id", "=", self.env.uid)]
        )
        by_token = {record.token: record for record in records}
        now = fields.Datetime.now()
        ordered = []
        for token in normalized:
            record = by_token.get(token)
            if not record or record.expires_at < now:
                raise AccessError("Assistant attachment not found")
            ordered.append(record)
        return self.browse([record.id for record in ordered])

    @api.model
    def _cron_cleanup_expired(self):
        cutoff = fields.Datetime.now()
        expired = self.with_user(SUPERUSER_ID).search(
            [("expires_at", "<", cutoff)],
            limit=100,
        )
        expired.unlink()


def _filename(value) -> str:
    if not isinstance(value, str):
        raise ValidationError("Knowledge filename is required")
    normalized = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not normalized or len(normalized) > _MAX_FILENAME or "\x00" in normalized:
        raise ValidationError("Invalid Knowledge filename")
    return normalized


def _mimetype(value, filename: str) -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.split(";", 1)[0].strip().lower()[:120]
    else:
        normalized = ""
    if normalized:
        return normalized
    extension = _extension(filename)
    defaults = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".rst": "text/x-rst",
        ".txt": "text/plain",
        ".xml": "application/xml",
    }
    return defaults.get(extension, "application/octet-stream")


def _extension(filename: str) -> str:
    position = filename.rfind(".")
    return filename[position:].lower() if position >= 0 else ""


def _validate_supported_document(filename: str, mimetype: str) -> None:
    if _extension(filename) not in _SUPPORTED_EXTENSIONS and mimetype not in _SUPPORTED_MIMETYPES:
        raise KnowledgeProcessingError("knowledge_unsupported_document")


def _decode_binary(value) -> bytes:
    if not value:
        raise KnowledgeProcessingError("knowledge_empty_upload")
    payload = value.encode("ascii") if isinstance(value, str) else value
    if not isinstance(payload, (bytes, bytearray)):
        raise KnowledgeProcessingError("knowledge_invalid_upload")
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as error:
        raise KnowledgeProcessingError("knowledge_invalid_upload") from error
    if not raw:
        raise KnowledgeProcessingError("knowledge_empty_upload")
    if len(raw) > _MAX_SOURCE_BYTES:
        raise KnowledgeProcessingError("knowledge_file_too_large")
    return raw


def _extract_text(raw: bytes) -> str:
    text = raw.decode("utf-8-sig", errors="replace").replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = text.strip()
    if len(text) > _MAX_SOURCE_TEXT_CHARS:
        raise KnowledgeProcessingError("knowledge_text_too_large")
    return text


def _chunk_text(text: str):
    if not text:
        return []
    blocks = []
    start = 0
    for match in re.finditer(r"\n\s*\n+", text):
        end = match.start()
        if end > start:
            blocks.append((start, text[start:end].strip()))
        start = match.end()
    if start < len(text):
        blocks.append((start, text[start:].strip()))
    if not blocks:
        blocks = [(0, text)]

    chunks = []
    buffer = ""
    buffer_start = 0
    for block_start, block in blocks:
        if not block:
            continue
        if len(block) > _MAX_CHUNK_CHARS:
            if buffer:
                chunks.append(_chunk_row(buffer_start, buffer))
                buffer = ""
            position = 0
            while position < len(block):
                part = block[position : position + _MAX_CHUNK_CHARS]
                chunks.append(_chunk_row(block_start + position, part))
                position += _MAX_CHUNK_CHARS
                if len(chunks) > _MAX_CHUNKS:
                    raise KnowledgeProcessingError("knowledge_too_many_chunks")
            continue
        candidate = f"{buffer}\n\n{block}" if buffer else block
        if len(candidate) > _MAX_CHUNK_CHARS and buffer:
            chunks.append(_chunk_row(buffer_start, buffer))
            buffer = block
            buffer_start = block_start
        else:
            if not buffer:
                buffer_start = block_start
            buffer = candidate
        if len(chunks) > _MAX_CHUNKS:
            raise KnowledgeProcessingError("knowledge_too_many_chunks")
    if buffer:
        chunks.append(_chunk_row(buffer_start, buffer))
    if len(chunks) > _MAX_CHUNKS:
        raise KnowledgeProcessingError("knowledge_too_many_chunks")
    return chunks


def _chunk_row(start: int, content: str):
    normalized = content.strip()
    return {
        "content": normalized,
        "char_start": max(0, int(start)),
        "char_end": max(0, int(start)) + len(normalized),
    }


__all__ = [
    "AssistantKnowledgeAttachment",
    "AssistantKnowledgeChunk",
    "AssistantKnowledgeSource",
    "KnowledgeProcessingError",
]
