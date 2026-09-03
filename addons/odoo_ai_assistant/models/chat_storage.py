"""Odoo-native persistence for Assistant conversations, messages, and turns."""

from __future__ import annotations

from uuid import UUID, uuid4

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AssistantConversation(models.Model):
    _name = "odoo.ai.conversation"
    _description = "Odoo AI Assistant Conversation"
    _order = "last_message_at desc, id desc"

    conversation_uuid = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: str(uuid4()),
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
    title = fields.Char(required=True, size=160)
    last_message_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    message_ids = fields.One2many(
        "odoo.ai.message",
        "conversation_id",
        string="Messages",
    )
    turn_ids = fields.One2many(
        "odoo.ai.turn",
        "conversation_id",
        string="Turns",
    )

    _sql_constraints = [
        (
            "conversation_uuid_unique",
            "unique(conversation_uuid)",
            "Conversation id must be unique.",
        ),
    ]

    @api.model
    def append_exchange(
        self,
        *,
        conversation_uuid,
        user_message,
        assistant_message,
        internal_workflow="AGENT",
    ):
        _validate_message(user_message)
        _validate_message(assistant_message, maximum=16_384)
        conversation = (
            self._owned_conversation(conversation_uuid)
            if conversation_uuid
            else self.create(
                {
                    "title": _title(user_message),
                    "last_message_at": fields.Datetime.now(),
                }
            )
        )
        message_model = self.env["odoo.ai.message"]
        message_model.create(
            [
                {
                    "conversation_id": conversation.id,
                    "role": "user",
                    "content": user_message,
                    "internal_workflow": internal_workflow,
                },
                {
                    "conversation_id": conversation.id,
                    "role": "assistant",
                    "content": assistant_message,
                    "internal_workflow": internal_workflow,
                },
            ]
        )
        conversation.write({"last_message_at": fields.Datetime.now()})
        return conversation.conversation_uuid

    @api.model
    def history_payload(
        self,
        *,
        conversation_uuid=None,
        max_conversations=20,
        max_messages=40,
    ):
        if not 1 <= int(max_conversations) <= 50 or not 1 <= int(max_messages) <= 80:
            raise ValidationError("Invalid history limit")
        domain = [("user_id", "=", self.env.uid)]
        conversations = self.search(
            domain,
            limit=int(max_conversations),
            order="last_message_at desc, id desc",
        )
        selected = self.browse()
        if conversation_uuid:
            selected = self._owned_conversation(conversation_uuid)
        messages = self.env["odoo.ai.message"].browse()
        if selected:
            newest = self.env["odoo.ai.message"].search(
                [
                    ("conversation_id", "=", selected.id),
                    ("user_id", "=", self.env.uid),
                ],
                limit=int(max_messages),
                order="create_date desc, id desc",
            )
            messages = newest.sorted(key=lambda item: (item.create_date, item.id))
        latest_turn = (
            self.env["odoo.ai.turn"].search(
                [
                    ("conversation_id", "=", selected.id),
                    ("user_id", "=", self.env.uid),
                    (
                        "state",
                        "in",
                        [
                            "queued",
                            "running",
                            "cancel_requested",
                            "awaiting_confirmation",
                            "recovery_required",
                        ],
                    ),
                ],
                order="id desc",
                limit=1,
            )
            if selected
            else self.env["odoo.ai.turn"].browse()
        )
        activity_by_message = self._history_activity_by_message(messages)
        attachments_by_message = self._history_attachments_by_message(messages)
        return {
            "active_conversation_id": (
                selected.conversation_uuid if selected else None
            ),
            "conversations": [item._history_view() for item in conversations],
            "messages": [
                item._history_view(
                    activity=activity_by_message.get(item.id),
                    attachments=attachments_by_message.get(item.id),
                )
                for item in messages
            ],
            "active_turn": (
                {"turn_id": latest_turn.turn_uuid, "state": latest_turn.state}
                if latest_turn
                else None
            ),
        }

    def _history_activity_by_message(self, messages):
        """Project the public, persisted activity that belongs to each Assistant answer.

        Live rows are already the browser-safe projection used while a turn runs. Reusing those
        rows keeps chat history aligned with the live UI without persisting private reasoning or
        introducing a second activity store.
        """

        assistant_ids = [item.id for item in messages if item.role == "assistant"]
        if not assistant_ids:
            return {}
        turns = self.env["odoo.ai.turn"].search(
            [
                ("assistant_message_id", "in", assistant_ids),
                ("user_id", "=", self.env.uid),
                ("conversation_id", "in", messages.mapped("conversation_id").ids),
            ],
            order="id asc",
        )
        live_model = self.env["odoo.ai.turn.live.event"]
        rows_by_turn = {}
        for row in live_model.search(
            [
                ("turn_ref_id", "in", turns.ids),
                ("channel", "in", ["activity", "reasoning"]),
            ],
            order="turn_ref_id, sequence",
        ):
            bucket = rows_by_turn.setdefault(row.turn_ref_id, [])
            if len(bucket) < 192:
                bucket.append(row)
        result = {}
        for turn in turns:
            events = []
            reasoning_parts = {}
            for row in rows_by_turn.get(turn.id, []):
                if row.turn_uuid != turn.turn_uuid:
                    continue
                if row.channel == "activity":
                    events.append(row.activity_browser_view())
                    continue
                item = row.live_browser_view()
                key = f"{item['item_id']}:{item['summary_index']}"
                reasoning_parts[key] = (reasoning_parts.get(key, "") + item["text"])[
                    :8_192
                ]
            if not events and not reasoning_parts:
                continue
            result[turn.assistant_message_id.id] = {
                "turn_id": turn.turn_uuid,
                "events": events[:100],
                "reasoning_summary_parts": [
                    {"key": key, "text": text}
                    for key, text in reasoning_parts.items()
                    if text
                ],
            }
        return result

    def _history_attachments_by_message(self, messages):
        user_ids = [item.id for item in messages if item.role == "user"]
        if not user_ids:
            return {}
        turns = self.env["odoo.ai.turn"].search(
            [
                ("user_message_id", "in", user_ids),
                ("user_id", "=", self.env.uid),
                ("conversation_id", "in", messages.mapped("conversation_id").ids),
            ],
            order="id asc",
        )
        result = {}
        for turn in turns:
            manifest = turn.knowledge_attachment_manifest
            if not isinstance(manifest, list):
                continue
            rows = []
            for item in manifest[:8]:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                mimetype = item.get("mimetype")
                size = item.get("size")
                if not isinstance(name, str) or not name.strip():
                    continue
                rows.append(
                    {
                        "name": name[:255],
                        "mimetype": mimetype[:120]
                        if isinstance(mimetype, str)
                        else "application/octet-stream",
                        "size": size if type(size) is int and size >= 0 else 0,
                    }
                )
            if rows:
                result[turn.user_message_id.id] = rows
        return result

    @api.model
    def recent_text(self, conversation_uuid, *, max_messages=8, max_chars=5_000):
        if not conversation_uuid:
            return ""
        conversation = self._owned_conversation(conversation_uuid)
        newest = self.env["odoo.ai.message"].search(
            [
                ("conversation_id", "=", conversation.id),
                ("user_id", "=", self.env.uid),
            ],
            limit=max_messages,
            order="create_date desc, id desc",
        )
        retained = []
        used = 0
        for item in newest:
            prefix = "User" if item.role == "user" else "Assistant"
            full_line = f"{prefix}: {item.content.strip()}"
            separator = 1 if retained else 0
            remaining = max_chars - used - separator
            if remaining <= 0:
                break
            line = full_line[:remaining]
            retained.append(line)
            used += separator + len(line)
            if len(line) < len(full_line):
                break
        return "\n".join(reversed(retained))

    @api.model
    def delete_owned(self, conversation_uuids):
        parsed = [_canonical_uuid(value) for value in conversation_uuids]
        if not 1 <= len(parsed) <= 50 or len(parsed) != len(set(parsed)):
            raise ValidationError("Invalid conversation selection")
        records = self.search(
            [
                ("conversation_uuid", "in", parsed),
                ("user_id", "=", self.env.uid),
            ]
        )
        if len(records) != len(parsed):
            raise AccessError("Conversation not found")
        count = len(records)
        records.unlink()
        return count

    def _owned_conversation(self, conversation_uuid):
        canonical = _canonical_uuid(conversation_uuid)
        record = self.search(
            [
                ("conversation_uuid", "=", canonical),
                ("user_id", "=", self.env.uid),
            ],
            limit=1,
        )
        if not record:
            raise AccessError("Conversation not found")
        return record

    def _history_view(self):
        self.ensure_one()
        return {
            "conversation_id": self.conversation_uuid,
            "title": self.title,
            "created_at": _iso_utc(self.create_date),
            "updated_at": _iso_utc(
                self.last_message_at or self.write_date or self.create_date
            ),
        }


class AssistantMessage(models.Model):
    _name = "odoo.ai.message"
    _description = "Odoo AI Assistant Message"
    _order = "create_date asc, id asc"

    message_uuid = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: str(uuid4()),
    )
    conversation_id = fields.Many2one(
        "odoo.ai.conversation",
        required=True,
        index=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        related="conversation_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="conversation_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    role = fields.Selection(
        [("user", "User"), ("assistant", "Assistant")],
        required=True,
        readonly=True,
    )
    content = fields.Text(required=True, readonly=True)
    internal_workflow = fields.Char(readonly=True)

    _sql_constraints = [
        (
            "message_uuid_unique",
            "unique(message_uuid)",
            "Message id must be unique.",
        ),
    ]

    def _history_view(self, *, activity=None, attachments=None):
        self.ensure_one()
        result = {
            "message_id": self.message_uuid,
            "role": self.role,
            "content": self.content,
            "created_at": _iso_utc(self.create_date),
        }
        if self.role == "assistant" and isinstance(activity, dict):
            result["activity"] = activity
        if self.role == "user" and isinstance(attachments, list) and attachments:
            result["attachments"] = attachments
        return result


class AssistantTurn(models.Model):
    _name = "odoo.ai.turn"
    _description = "Odoo AI Assistant Turn"
    _order = "queued_at desc, id desc"

    turn_uuid = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: str(uuid4()),
    )
    conversation_id = fields.Many2one(
        "odoo.ai.conversation",
        index=True,
        ondelete="set null",
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
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("cancel_requested", "Cancellation requested"),
            ("awaiting_confirmation", "Awaiting confirmation"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
            ("recovery_required", "Recovery required"),
        ],
        required=True,
        default="queued",
        index=True,
    )
    input_message = fields.Text(readonly=True)
    screen_payload = fields.Json(readonly=True)
    allowed_company_ids = fields.Json(readonly=True)
    lang = fields.Char(readonly=True, size=35)
    tz = fields.Char(readonly=True, size=64)
    reasoning_model = fields.Char(readonly=True, size=128)
    policy_payload = fields.Json(readonly=True)
    request_fingerprint = fields.Char(readonly=True, index=True, size=71)
    client_request_id = fields.Char(readonly=True, index=True, size=128)
    user_message_id = fields.Many2one(
        "odoo.ai.message",
        readonly=True,
        ondelete="set null",
    )
    assistant_message_id = fields.Many2one(
        "odoo.ai.message",
        readonly=True,
        ondelete="set null",
    )
    result_payload = fields.Json(readonly=True)
    queued_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    started_at = fields.Datetime(index=True)
    heartbeat_at = fields.Datetime(index=True)
    lease_expires_at = fields.Datetime(index=True)
    lease_token = fields.Char(readonly=True, index=True, size=64)
    attempt_count = fields.Integer(required=True, readonly=True, default=0)
    max_attempts = fields.Integer(required=True, readonly=True, default=2)
    write_barrier = fields.Boolean(required=True, readonly=True, default=False)
    cancel_requested_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    error_code = fields.Char(readonly=True, size=128)
    last_event_sequence = fields.Integer(
        required=True,
        readonly=True,
        default=0,
    )
    event_ids = fields.One2many(
        "odoo.ai.turn.event",
        "turn_id",
        string="Events",
        readonly=True,
    )

    _sql_constraints = [
        (
            "turn_uuid_unique",
            "unique(turn_uuid)",
            "Turn id must be unique.",
        ),
        (
            "turn_user_client_request_unique",
            "unique(user_id, client_request_id)",
            "Assistant request id must be unique per user.",
        ),
        (
            "turn_attempts_nonnegative",
            "CHECK(attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts)",
            "Assistant turn attempt counters are invalid.",
        ),
        (
            "turn_event_sequence_nonnegative",
            "CHECK(last_event_sequence >= 0)",
            "Assistant event cursor is invalid.",
        ),
    ]


def _title(message):
    normalized = " ".join(message.split())
    return normalized if len(normalized) <= 80 else normalized[:79].rstrip() + "…"


def _validate_message(value, *, maximum=4_000):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= maximum
        or "\x00" in value
    ):
        raise ValidationError("Invalid chat message")


def _canonical_uuid(value):
    if not isinstance(value, str):
        raise ValidationError("Invalid conversation id")
    try:
        parsed = str(UUID(value))
    except ValueError as error:
        raise ValidationError("Invalid conversation id") from error
    if parsed != value:
        raise ValidationError("Invalid conversation id")
    return parsed


def _iso_utc(value):
    if not value:
        return ""
    parsed = fields.Datetime.to_datetime(value)
    return parsed.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"
