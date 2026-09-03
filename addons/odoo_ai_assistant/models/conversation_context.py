"""P5.6 bounded durable conversation context for embedded Assistant turns."""

from __future__ import annotations

import json
import re
from copy import deepcopy

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError

_CONTEXT_FORMAT_VERSION = 1
_CONTEXT_HOST_WRITE = "_odoo_ai_context_host_write"
_TERMINAL_TURN_STATES = frozenset(
    {"completed", "failed", "cancelled", "recovery_required"}
)

_MAX_PREDECESSOR_SCAN = 24
_MAX_RECENT_MESSAGES = 6
_MAX_RECENT_CONTENT = 640
_MAX_ROLLING_SUMMARY = 6
_MAX_USER_INTENT = 180
_MAX_ASSISTANT_OUTCOME = 240
_MAX_ACTIVE_REFS = 8
_MAX_EFFECT_REFS = 8
_MAX_EVIDENCE_REFS = 8
_MAX_SESSION_SETTINGS = 8
_MAX_PROVIDER_CONTEXT_CHARS = 8_000

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_SETTING_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_MODEL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


class AssistantTurnConversationContext(models.Model):
    """Immutable per-turn context checkpoints derived from Odoo-owned history.

    Full messages and turns remain history authority. Each checkpoint is a bounded
    projection used by the reasoning provider and can be reconstructed from causal
    predecessor turns; Codex threads never become persistence authority.
    """

    _inherit = "odoo.ai.turn"

    conversation_context_payload = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(_CONTEXT_HOST_WRITE):
            for values in vals_list:
                if "conversation_context_payload" in values:
                    raise ValidationError("Assistant turn context is host-managed")
        return super().create(vals_list)

    def write(self, values):
        if (
            "conversation_context_payload" in values
            and not self.env.context.get(_CONTEXT_HOST_WRITE)
        ):
            raise ValidationError("Assistant turn context is host-managed")
        if "conversation_context_payload" in values:
            for record in self:
                current = record.conversation_context_payload
                if current and values["conversation_context_payload"] != current:
                    raise ValidationError(
                        "Assistant turn conversation context is immutable"
                    )
        return super().write(values)

    def conversation_context_snapshot(self):
        """Capture context once for this turn and reuse it on resume/post-effect."""

        self.ensure_one()
        if self.conversation_context_payload:
            return _validate_snapshot(self.conversation_context_payload)
        if not self.conversation_id:
            return None

        snapshot = self._build_conversation_context_snapshot()
        self.with_user(SUPERUSER_ID).with_context(
            **{_CONTEXT_HOST_WRITE: True}
        ).write({"conversation_context_payload": snapshot})
        return deepcopy(snapshot)

    def conversation_context_for_provider(self):
        self.ensure_one()
        snapshot = self.conversation_context_snapshot()
        return "" if snapshot is None else _provider_context_json(snapshot)

    def _build_conversation_context_snapshot(self):
        self.ensure_one()
        predecessors = self.env["odoo.ai.turn"].search(
            [
                ("conversation_id", "=", self.conversation_id.id),
                ("id", "<", self.id),
            ],
            limit=_MAX_PREDECESSOR_SCAN,
            order="id desc",
        ).sorted(key=lambda item: item.id)

        if any(item.state not in _TERMINAL_TURN_STATES for item in predecessors):
            raise ValidationError(
                "Assistant conversation has a non-terminal causal predecessor"
            )

        base, fold_from = _base_checkpoint(
            predecessors,
            conversation_uuid=self.conversation_id.conversation_uuid,
        )
        for predecessor in predecessors[fold_from:]:
            base = _fold_turn(base, predecessor)

        snapshot = {
            "format_version": _CONTEXT_FORMAT_VERSION,
            "conversation_id": self.conversation_id.conversation_uuid,
            "revision": base["revision"],
            "recent_messages": _recent_causal_messages(predecessors),
            "rolling_summary": deepcopy(base["rolling_summary"]),
            "active_refs": _merge_refs(
                base["active_refs"],
                _screen_refs(self.screen_payload or {}),
            ),
            "evidence_refs": deepcopy(base["evidence_refs"]),
            "verified_effect_refs": deepcopy(base["verified_effect_refs"]),
            "session_settings": _session_settings_for_turn(
                base["session_settings"],
                self.lang,
            ),
        }
        return _validate_snapshot(snapshot)


class EmbeddedAssistantConversationContext(models.AbstractModel):
    """Install the structured checkpoint at the existing provider context seam."""

    _inherit = "odoo.ai.embedded.runtime"

    def _conversation_summary(self, turn):
        return turn.conversation_context_for_provider()


def _empty_context(conversation_uuid):
    return {
        "format_version": _CONTEXT_FORMAT_VERSION,
        "conversation_id": conversation_uuid,
        "revision": 0,
        "recent_messages": [],
        "rolling_summary": [],
        "active_refs": [],
        "evidence_refs": [],
        "verified_effect_refs": [],
        "session_settings": {},
    }


def _base_checkpoint(predecessors, *, conversation_uuid):
    """Reuse the newest valid checkpoint and fold its owning turn plus successors."""

    for index in range(len(predecessors) - 1, -1, -1):
        payload = predecessors[index].conversation_context_payload
        if not payload:
            continue
        validated = _validate_snapshot(payload)
        if validated["conversation_id"] != conversation_uuid:
            raise ValidationError("Assistant conversation context binding mismatch")
        return validated, index
    return _empty_context(conversation_uuid), 0


def _fold_turn(context, turn):
    current = _validate_snapshot(context)
    current["revision"] += 1
    current["rolling_summary"] = _bounded_tail(
        [*current["rolling_summary"], _turn_summary(turn)],
        _MAX_ROLLING_SUMMARY,
    )
    current["active_refs"] = _merge_refs(
        current["active_refs"],
        _screen_refs(turn.screen_payload or {}),
    )
    current["verified_effect_refs"] = _merge_effect_refs(
        current["verified_effect_refs"],
        _verified_effect_refs(turn),
    )
    # Recent raw messages are rebuilt from authoritative predecessor turns for every
    # checkpoint instead of being recursively copied.
    current["recent_messages"] = []
    return current


def _recent_causal_messages(predecessors):
    """Return messages in turn-causal order, not raw message creation order.

    A later user turn can be queued before the previous Assistant reply is persisted.
    Ordering only by message id/create_date would therefore put future text in the wrong
    causal position. Turn identity/order is the stable source of ordering here.
    """

    messages = []
    for predecessor in predecessors:
        for message in (
            predecessor.user_message_id,
            predecessor.assistant_message_id,
        ):
            if message:
                messages.append(_message_context(message))
    return _bounded_tail(messages, _MAX_RECENT_MESSAGES)


def _session_settings_for_turn(existing, lang):
    settings = deepcopy(existing)
    if isinstance(lang, str) and lang and len(lang) <= 35 and "\x00" not in lang:
        settings["odoo_user_language"] = lang
    elif not lang:
        settings["odoo_user_language"] = False
    return settings


def _message_context(message):
    if message.role not in {"user", "assistant"}:
        raise ValidationError("Invalid Assistant message role in conversation context")
    return {
        "message_id": message.message_uuid,
        "role": message.role,
        "content": _excerpt(message.content, _MAX_RECENT_CONTENT),
    }


def _turn_summary(turn):
    user_text = (
        turn.user_message_id.content
        if turn.user_message_id
        else (turn.input_message or "")
    )
    assistant_text = (
        turn.assistant_message_id.content
        if turn.assistant_message_id
        else ""
    )
    failure_code = turn.error_code or None
    if failure_code is not None and (
        not isinstance(failure_code, str)
        or not _SAFE_TOKEN.fullmatch(failure_code)
    ):
        failure_code = None
    return {
        "turn_id": turn.turn_uuid,
        "state": turn.state,
        "user_intent": _excerpt(user_text, _MAX_USER_INTENT),
        "assistant_outcome": _excerpt(
            assistant_text,
            _MAX_ASSISTANT_OUTCOME,
        ),
        "failure_code": failure_code,
    }


def _screen_refs(screen):
    if not isinstance(screen, dict):
        return []
    model = screen.get("model")
    if not isinstance(model, str) or not _MODEL_NAME.fullmatch(model):
        return []

    refs = []
    res_id = screen.get("res_id")
    if type(res_id) is int and res_id > 0:
        refs.append({"kind": "odoo_record", "model": model, "res_id": res_id})
    selected = screen.get("selected_ids")
    if isinstance(selected, list):
        for record_id in selected:
            if type(record_id) is int and record_id > 0:
                refs.append(
                    {
                        "kind": "odoo_record",
                        "model": model,
                        "res_id": record_id,
                    }
                )
    if not refs:
        refs.append({"kind": "odoo_model", "model": model, "res_id": None})
    return refs


def _merge_refs(existing, new):
    merged = []
    positions = {}
    for item in [*existing, *new]:
        _validate_active_ref(item)
        key = (item["kind"], item["model"], item["res_id"])
        if key in positions:
            merged.pop(positions[key])
            positions = {
                (row["kind"], row["model"], row["res_id"]): index
                for index, row in enumerate(merged)
            }
        merged.append(dict(item))
        positions[key] = len(merged) - 1
    return _bounded_tail(merged, _MAX_ACTIVE_REFS)


def _verified_effect_refs(turn):
    envelope = turn.capability_plan_payload
    if not isinstance(envelope, dict):
        return []
    plan = envelope.get("plan")
    if not isinstance(plan, dict) or plan.get("state") != "completed":
        return []
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return []

    refs = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict) or step.get("state") != "completed":
            continue
        capability = step.get("capability")
        if not isinstance(capability, str) or not _SAFE_TOKEN.fullmatch(capability):
            continue
        position = step.get("position")
        if type(position) is not int or position <= 0:
            position = index
        ref = {
            "turn_id": turn.turn_uuid,
            "position": position,
            "capability": capability,
            "state": "completed",
        }
        result = step.get("result")
        resource = _effect_resource(result)
        if resource is not None:
            ref["resource"] = resource
        operation = result.get("operation") if isinstance(result, dict) else None
        if isinstance(operation, str) and _SAFE_TOKEN.fullmatch(operation):
            ref["operation"] = operation
        refs.append(ref)
    return _bounded_tail(refs, _MAX_EFFECT_REFS)


def _merge_effect_refs(existing, new):
    merged = []
    keys = set()
    for item in [*existing, *new]:
        _validate_effect_ref(item)
        key = (item["turn_id"], item["position"], item["capability"])
        if key in keys:
            merged = [
                row
                for row in merged
                if (row["turn_id"], row["position"], row["capability"]) != key
            ]
        merged.append(dict(item))
        keys = {
            (row["turn_id"], row["position"], row["capability"])
            for row in merged
        }
    return _bounded_tail(merged, _MAX_EFFECT_REFS)


def _validate_snapshot(value):
    required = set(_empty_context("placeholder"))
    if not isinstance(value, dict) or set(value) != required:
        raise ValidationError("Invalid Assistant turn conversation context")
    if value.get("format_version") != _CONTEXT_FORMAT_VERSION:
        raise ValidationError("Unsupported Assistant turn conversation context")
    if not isinstance(value.get("conversation_id"), str):
        raise ValidationError("Invalid Assistant conversation id in context")
    if type(value.get("revision")) is not int or value["revision"] < 0:
        raise ValidationError("Invalid Assistant turn context revision")

    recent = value.get("recent_messages")
    if not isinstance(recent, list) or len(recent) > _MAX_RECENT_MESSAGES:
        raise ValidationError("Invalid Assistant recent conversation messages")
    for item in recent:
        _validate_message_item(item)

    rolling = value.get("rolling_summary")
    if not isinstance(rolling, list) or len(rolling) > _MAX_ROLLING_SUMMARY:
        raise ValidationError("Invalid Assistant rolling conversation summary")
    for item in rolling:
        _validate_summary_item(item)

    active_refs = value.get("active_refs")
    if not isinstance(active_refs, list) or len(active_refs) > _MAX_ACTIVE_REFS:
        raise ValidationError("Invalid Assistant active references")
    for item in active_refs:
        _validate_active_ref(item)

    evidence_refs = value.get("evidence_refs")
    if not isinstance(evidence_refs, list) or len(evidence_refs) > _MAX_EVIDENCE_REFS:
        raise ValidationError("Invalid Assistant evidence references")
    for item in evidence_refs:
        _validate_evidence_ref(item)

    effect_refs = value.get("verified_effect_refs")
    if not isinstance(effect_refs, list) or len(effect_refs) > _MAX_EFFECT_REFS:
        raise ValidationError("Invalid Assistant verified effect references")
    for item in effect_refs:
        _validate_effect_ref(item)

    _validate_session_settings(value.get("session_settings"))
    return deepcopy(value)


def _validate_message_item(item):
    if not isinstance(item, dict) or set(item) != {"message_id", "role", "content"}:
        raise ValidationError("Invalid Assistant recent conversation message")
    if not isinstance(item["message_id"], str) or not 1 <= len(item["message_id"]) <= 64:
        raise ValidationError("Invalid Assistant recent message id")
    if item["role"] not in {"user", "assistant"}:
        raise ValidationError("Invalid Assistant recent message role")
    if not isinstance(item["content"], str) or len(item["content"]) > _MAX_RECENT_CONTENT:
        raise ValidationError("Invalid Assistant recent message content")


def _validate_summary_item(item):
    required = {
        "turn_id",
        "state",
        "user_intent",
        "assistant_outcome",
        "failure_code",
    }
    if not isinstance(item, dict) or set(item) != required:
        raise ValidationError("Invalid Assistant conversation summary item")
    if not isinstance(item["turn_id"], str) or not 1 <= len(item["turn_id"]) <= 64:
        raise ValidationError("Invalid Assistant summary turn id")
    if item["state"] not in _TERMINAL_TURN_STATES:
        raise ValidationError("Invalid Assistant summary turn state")
    if (
        not isinstance(item["user_intent"], str)
        or len(item["user_intent"]) > _MAX_USER_INTENT
        or not isinstance(item["assistant_outcome"], str)
        or len(item["assistant_outcome"]) > _MAX_ASSISTANT_OUTCOME
    ):
        raise ValidationError("Invalid Assistant conversation summary text")
    failure = item["failure_code"]
    if failure is not None and (
        not isinstance(failure, str) or not _SAFE_TOKEN.fullmatch(failure)
    ):
        raise ValidationError("Invalid Assistant summary failure code")


def _validate_active_ref(item):
    if not isinstance(item, dict) or set(item) != {"kind", "model", "res_id"}:
        raise ValidationError("Invalid Assistant active reference")
    if item["kind"] not in {"odoo_model", "odoo_record"}:
        raise ValidationError("Invalid Assistant active reference kind")
    if not isinstance(item["model"], str) or not _MODEL_NAME.fullmatch(item["model"]):
        raise ValidationError("Invalid Assistant active reference model")
    record_id = item["res_id"]
    if item["kind"] == "odoo_model":
        if record_id is not None:
            raise ValidationError("Invalid Assistant model reference")
    elif type(record_id) is not int or record_id <= 0:
        raise ValidationError("Invalid Assistant record reference")


def _validate_evidence_ref(item):
    if not isinstance(item, dict) or set(item) != {"kind", "ref"}:
        raise ValidationError("Invalid Assistant evidence reference")
    for key in ("kind", "ref"):
        value = item[key]
        if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
            raise ValidationError("Invalid Assistant evidence reference")


def _validate_effect_ref(item):
    required = {"turn_id", "position", "capability", "state"}
    optional = {"operation", "resource"}
    if not isinstance(item, dict) or not required <= set(item) <= required | optional:
        raise ValidationError("Invalid Assistant verified effect reference")
    if not isinstance(item["turn_id"], str) or not 1 <= len(item["turn_id"]) <= 64:
        raise ValidationError("Invalid Assistant effect turn id")
    if type(item["position"]) is not int or item["position"] <= 0:
        raise ValidationError("Invalid Assistant effect position")
    if (
        not isinstance(item["capability"], str)
        or not _SAFE_TOKEN.fullmatch(item["capability"])
        or item["state"] != "completed"
    ):
        raise ValidationError("Invalid Assistant effect reference")
    operation = item.get("operation")
    if operation is not None and (
        not isinstance(operation, str) or not _SAFE_TOKEN.fullmatch(operation)
    ):
        raise ValidationError("Invalid Assistant effect operation")
    resource = item.get("resource")
    if resource is not None:
        _validate_effect_resource(resource)


def _effect_resource(result):
    if not isinstance(result, dict):
        return None
    model = result.get("model")
    if not isinstance(model, str) or not _MODEL_NAME.fullmatch(model):
        return None
    record_ids = result.get("record_ids")
    if not isinstance(record_ids, list):
        record_id = result.get("record_id")
        record_ids = [record_id] if type(record_id) is int else []
    normalized = []
    seen = set()
    for record_id in record_ids:
        if type(record_id) is not int or record_id <= 0 or record_id in seen:
            return None
        normalized.append(record_id)
        seen.add(record_id)
    if not normalized or len(normalized) > 500:
        return None
    return {"model": model, "record_ids": normalized}


def _validate_effect_resource(resource):
    if not isinstance(resource, dict) or set(resource) != {"model", "record_ids"}:
        raise ValidationError("Invalid Assistant effect resource")
    model = resource.get("model")
    record_ids = resource.get("record_ids")
    if (
        not isinstance(model, str)
        or not _MODEL_NAME.fullmatch(model)
        or not isinstance(record_ids, list)
        or not 1 <= len(record_ids) <= 500
        or any(type(record_id) is not int or record_id <= 0 for record_id in record_ids)
        or len(set(record_ids)) != len(record_ids)
    ):
        raise ValidationError("Invalid Assistant effect resource")


def _validate_session_settings(value):
    if not isinstance(value, dict) or len(value) > _MAX_SESSION_SETTINGS:
        raise ValidationError("Invalid Assistant conversation session settings")
    for key, item in value.items():
        if not isinstance(key, str) or not _SAFE_SETTING_KEY.fullmatch(key):
            raise ValidationError("Invalid Assistant conversation setting key")
        if item is None or type(item) in {bool, int}:
            continue
        if isinstance(item, str) and len(item) <= 128 and "\x00" not in item:
            continue
        raise ValidationError("Invalid Assistant conversation setting value")


def _provider_context_json(snapshot):
    compact = _validate_snapshot(snapshot)
    while True:
        encoded = json.dumps(
            compact,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(encoded) <= _MAX_PROVIDER_CONTEXT_CHARS:
            return encoded
        if len(compact["recent_messages"]) > 2:
            compact["recent_messages"].pop(0)
            continue
        if len(compact["rolling_summary"]) > 2:
            compact["rolling_summary"].pop(0)
            continue
        if compact["active_refs"]:
            compact["active_refs"].pop(0)
            continue
        if compact["verified_effect_refs"]:
            compact["verified_effect_refs"].pop(0)
            continue
        if compact["evidence_refs"]:
            compact["evidence_refs"].pop(0)
            continue
        raise ValidationError("Assistant conversation context is too large")


def _excerpt(value, maximum):
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.replace("\x00", "").split())
    if len(normalized) <= maximum:
        return normalized
    return normalized[: maximum - 1].rstrip() + "…"


def _bounded_tail(items, maximum):
    return [deepcopy(item) for item in items[-maximum:]]
