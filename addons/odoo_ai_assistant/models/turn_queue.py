"""Persistent Odoo-native queue and recovery control plane for Assistant turns."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import timedelta
from uuid import UUID

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry

from ..services.screen_context import (
    ScreenContextValidationError,
    validate_query_screen,
)

_logger = logging.getLogger(__name__)

_MAX_MESSAGE = 4_000
_MAX_SCREEN_BYTES = 16 * 1024
_MAX_EVENTS_PAGE = 100
# One transient planning retry plus the normal post-approval execution claim must fit.
_MAX_ATTEMPTS = 3
# Explicit user redirects may require a new provider claim. They remain bounded separately from
# automatic retries, and each stale-decision requeue grows this ceiling by at most one.
_MAX_ATTEMPTS_WITH_REDIRECTS = _MAX_ATTEMPTS + 16
_LEASE_SECONDS = 300
_STALE_SCAN_LIMIT = 25
_CLIENT_REQUEST_ID = "^[A-Za-z0-9_.:-]{8,128}$"
_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,128}$")
_NON_RETRYABLE_TURN_ERRORS = frozenset(
    {
        "access_denied",
        "agent_capability_call_budget_exceeded",
        "agent_correctable_failure_budget_exceeded",
        "agent_provider_decision_budget_exceeded",
        "agent_task_plan_invalid",
        "agent_task_plan_revision_invalid",
        "capability_authority_mismatch",
        "capability_not_available",
        "capability_plan_approval_required",
        "capability_plan_binding_mismatch",
        "capability_plan_corrupt",
        "capability_plan_not_authorized",
        "capability_plan_precondition_changed",
        "capability_plan_version_mismatch",
        "capability_verification_failed",
    }
)


class AssistantTurnQueue(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def enqueue_for_current_user(
        self,
        *,
        message,
        screen,
        conversation_uuid=None,
        client_request_id=None,
    ):
        """Persist a user turn and wake the native scheduler without running the model."""

        if not self.env.user._is_internal():
            raise AccessError("Assistant is only available to internal users")
        _validate_message(message)
        try:
            validated_screen = validate_query_screen(screen)
        except ScreenContextValidationError as error:
            raise ValidationError("Invalid Assistant screen context") from error
        screen_payload = validated_screen.to_mapping()
        _validate_json_bytes(screen_payload, maximum=_MAX_SCREEN_BYTES)

        conversation_model = self.env["odoo.ai.conversation"]
        if conversation_uuid:
            conversation = conversation_model._owned_conversation(conversation_uuid)
        else:
            conversation = conversation_model.create(
                {
                    "title": _title(message),
                    "last_message_at": fields.Datetime.now(),
                }
            )

        if client_request_id:
            client_request_id = _validate_client_request_id(client_request_id)
            existing = self.search(
                [
                    ("user_id", "=", self.env.uid),
                    ("client_request_id", "=", client_request_id),
                ],
                limit=1,
            )
            if existing:
                return existing.browser_status(after_sequence=0)

        user_message = self.env["odoo.ai.message"].create(
            {
                "conversation_id": conversation.id,
                "role": "user",
                "content": message,
                "internal_workflow": "AGENT",
            }
        )
        allowed_company_ids = tuple(sorted(set(self.env.companies.ids)))
        if self.env.company.id not in allowed_company_ids:
            raise AccessError("Invalid company context")
        preference = self.env["odoo.ai.user.preference"]
        policy = self.env["odoo.ai.chat.policy"].policy_layers_for_turn(
            conversation_id=conversation.conversation_uuid,
            message=message,
        )
        request_fingerprint = _request_fingerprint(
            uid=self.env.uid,
            company_id=self.env.company.id,
            allowed_company_ids=allowed_company_ids,
            message=message,
            screen=screen_payload,
            conversation_uuid=conversation.conversation_uuid,
        )
        values = {
            "turn_uuid": str(_new_uuid()),
            "conversation_id": conversation.id,
            "user_id": self.env.uid,
            "company_id": self.env.company.id,
            "state": "queued",
            "queued_at": fields.Datetime.now(),
            "input_message": message,
            "screen_payload": screen_payload,
            "allowed_company_ids": list(allowed_company_ids),
            "lang": self.env.lang or False,
            "tz": self.env.context.get("tz") or self.env.user.tz or False,
            "reasoning_model": preference.current_reasoning_model() or False,
            "policy_payload": policy,
            "user_message_id": user_message.id,
            "client_request_id": client_request_id or False,
            "request_fingerprint": request_fingerprint,
            "max_attempts": _MAX_ATTEMPTS,
        }
        turn = self.with_user(SUPERUSER_ID).create(values)
        conversation.write({"last_message_at": fields.Datetime.now()})
        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=turn,
            event_type="queued",
            title="Petición en cola",
        )
        self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_1")._trigger()
        self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_2")._trigger()
        return turn.browser_status(after_sequence=0)

    def browser_status(self, *, after_sequence=0):
        self.ensure_one()
        self.check_access("read")
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValidationError("Invalid Assistant event cursor")
        events = self.env["odoo.ai.turn.event"].search(
            [
                ("turn_id", "=", self.id),
                ("sequence", ">", after_sequence),
            ],
            order="sequence",
            limit=_MAX_EVENTS_PAGE,
        )
        response = (
            self.result_payload
            if self.state in {"awaiting_confirmation", "completed"}
            else None
        )
        return {
            "ok": True,
            "turn_id": self.turn_uuid,
            "conversation_id": (
                self.conversation_id.conversation_uuid if self.conversation_id else None
            ),
            "state": self.state,
            "answer": self.assistant_message_id.content if self.assistant_message_id else None,
            "error_code": self.error_code or None,
            "response": dict(response) if isinstance(response, dict) else None,
            "last_sequence": self.last_event_sequence,
            "events": [event.browser_view() for event in events],
            "has_more_events": bool(
                events
                and events[-1].sequence < self.last_event_sequence
                and len(events) >= _MAX_EVENTS_PAGE
            ),
        }

    @api.model
    def status_for_current_user(self, turn_uuid, *, after_sequence=0):
        turn = self._owned_turn(turn_uuid)
        return turn.browser_status(after_sequence=after_sequence)

    @api.model
    def cancel_for_current_user(self, turn_uuid):
        turn = self._owned_turn(turn_uuid)
        if turn.state in {"completed", "failed", "cancelled", "recovery_required"}:
            return turn.browser_status(after_sequence=0)
        if turn.state == "queued":
            turn.with_user(SUPERUSER_ID).write(
                {
                    "state": "cancelled",
                    "cancel_requested_at": fields.Datetime.now(),
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="cancelled",
                title="Petición cancelada",
            )
        elif turn.state != "cancel_requested":
            turn.with_user(SUPERUSER_ID).write(
                {
                    "state": "cancel_requested",
                    "cancel_requested_at": fields.Datetime.now(),
                }
            )
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="cancel_requested",
                title="Cancelación solicitada",
            )
        return turn.browser_status(after_sequence=0)

    @api.model
    def _cron_run_turn_slot(self):
        """Claim at most one turn; two cron slots provide bounded concurrency."""

        dbname = self.env.cr.dbname
        _recover_stale_turns(dbname)
        claimed = _claim_next_turn(dbname)
        if not claimed:
            return
        turn_id, lease_token = claimed
        try:
            _execute_claimed_turn(dbname, turn_id, lease_token)
        except Exception as error:
            code = _runtime_error_code(error)
            _logger.exception("Embedded Assistant turn %s crashed: %s", turn_id, code)
            _fail_claimed_turn(dbname, turn_id, lease_token, code)

    @api.model
    def _owned_turn(self, turn_uuid):
        canonical = _canonical_uuid(turn_uuid)
        turn = self.search(
            [("turn_uuid", "=", canonical), ("user_id", "=", self.env.uid)],
            limit=1,
        )
        if not turn:
            raise AccessError("Assistant turn not found")
        return turn


def _claim_next_turn(dbname):
    with Registry(dbname).cursor() as cr:
        cr.execute(
            """
            SELECT id
              FROM odoo_ai_turn
             WHERE state = 'queued'
               AND attempt_count < max_attempts
             ORDER BY queued_at, id
             FOR UPDATE SKIP LOCKED
             LIMIT 1
            """
        )
        row = cr.fetchone()
        if not row:
            return None
        turn_id = row[0]
        lease_token = secrets.token_urlsafe(24)
        now = fields.Datetime.now()
        expires_at = now + timedelta(seconds=_LEASE_SECONDS)
        cr.execute(
            """
            UPDATE odoo_ai_turn
               SET state = 'running',
                   attempt_count = attempt_count + 1,
                   started_at = COALESCE(started_at, %s),
                   heartbeat_at = %s,
                   lease_expires_at = %s,
                   lease_token = %s,
                   write_date = %s
             WHERE id = %s
            """,
            [now, now, expires_at, lease_token, now, turn_id],
        )
        cr.commit()
    _append_event(dbname, turn_id, "started", "Procesando petición")
    return turn_id, lease_token


def _execute_claimed_turn(dbname, turn_id, lease_token):
    """Run the embedded composition root under the originating Odoo user.

    For a completed turn, business effects, verification, final message and result/status are
    committed by the same cursor. The separately committed write barrier remains the recovery
    boundary if the worker is lost before that transaction finishes.
    """

    if _cancellation_requested(dbname, turn_id, lease_token):
        _cancel_claimed_turn(dbname, turn_id, lease_token)
        return

    completed = False
    with Registry(dbname).cursor() as cr:
        control = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = control["odoo.ai.turn"].browse(turn_id).exists()
        if (
            not turn
            or turn.state != "running"
            or turn.lease_token != lease_token
        ):
            return
        user = turn.user_id.exists()
        if not user or not user.active:
            raise AccessError("Assistant user is no longer active")
        current_allowed = set(user.company_ids.ids)
        allowed_company_ids = tuple(
            company_id
            for company_id in (turn.allowed_company_ids or [])
            if company_id in current_allowed
        )
        if turn.company_id.id not in allowed_company_ids or not allowed_company_ids:
            raise AccessError("Assistant company context is no longer authorized")
        context = {
            "allowed_company_ids": list(allowed_company_ids),
            "lang": turn.lang or user.lang,
            "tz": turn.tz or user.tz,
        }
        user_env = api.Environment(cr, user.id, context, su=False)
        if user_env.su:
            raise AccessError("Assistant user environment must not use superuser mode")
        result = user_env["odoo.ai.embedded.runtime"].run_turn(
            turn_id=turn.id,
            lease_token=lease_token,
        )
        if not isinstance(result, dict):
            raise ValidationError("Invalid embedded Assistant result")

        turn.invalidate_recordset(
            ["state", "lease_token", "assistant_message_id", "result_payload"]
        )
        if turn.state == "running" and turn.lease_token == lease_token:
            _stage_completed_turn(control, turn, result)
            completed = True
        elif turn.state != "awaiting_confirmation":
            raise ValidationError("Embedded Assistant returned from an invalid turn state")
        cr.commit()

    if completed:
        _append_event(dbname, turn_id, "completed", "Respuesta completada")


def _stage_completed_turn(env, turn, result):
    answer = result.get("answer")
    if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 16_384:
        raise ValidationError("Invalid embedded Assistant answer")
    assistant_message = turn.assistant_message_id
    if assistant_message:
        assistant_message.write({"content": answer})
    else:
        assistant_message = env["odoo.ai.message"].create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "assistant",
                "content": answer,
                "internal_workflow": "AGENT",
            }
        )
    turn.write(
        {
            "state": "completed",
            "assistant_message_id": assistant_message.id,
            "result_payload": result,
            "completed_at": fields.Datetime.now(),
            "lease_token": False,
            "lease_expires_at": False,
            "heartbeat_at": fields.Datetime.now(),
        }
    )
    if turn.conversation_id:
        turn.conversation_id.write({"last_message_at": fields.Datetime.now()})


def _fail_claimed_turn(dbname, turn_id, lease_token, error_code):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn or turn.lease_token != lease_token:
            return
        if turn.state == "cancel_requested" or _control_cancel_requested_in_env(env, turn):
            _finalize_interrupted_answer(turn)
            turn.write(
                {
                    "state": "cancelled",
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            cr.commit()
            _append_event(dbname, turn_id, "cancelled", "Petición cancelada")
            return
        retryable = error_code not in _NON_RETRYABLE_TURN_ERRORS
        if (
            error_code == "agent_redirected"
            and not turn.write_barrier
            and turn.max_attempts < _MAX_ATTEMPTS_WITH_REDIRECTS
            and turn.attempt_count >= turn.max_attempts
        ):
            turn.write({"max_attempts": min(_MAX_ATTEMPTS_WITH_REDIRECTS, turn.max_attempts + 1)})
        if retryable and not turn.write_barrier and turn.attempt_count < turn.max_attempts:
            turn.write(
                {
                    "state": "queued",
                    "queued_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                    "error_code": False,
                }
            )
            cr.commit()
            _append_event(
                dbname,
                turn_id,
                "requeued",
                "Reintentando petición",
                diagnostic_code=error_code,
            )
            _trigger_turn_crons(dbname)
            return
        target_state = "recovery_required" if turn.write_barrier else "failed"
        turn.write(
            {
                "state": target_state,
                "error_code": error_code,
                "completed_at": fields.Datetime.now(),
                "lease_token": False,
                "lease_expires_at": False,
            }
        )
        cr.commit()
    _append_event(
        dbname,
        turn_id,
        target_state,
        "La petición requiere revisión"
        if target_state == "recovery_required"
        else "No se pudo completar la petición",
        diagnostic_code=error_code,
    )


def _recover_stale_turns(dbname):
    now = fields.Datetime.now()
    with Registry(dbname).cursor() as cr:
        cr.execute(
            """
            SELECT id
              FROM odoo_ai_turn
             WHERE state IN ('running', 'cancel_requested')
               AND lease_expires_at IS NOT NULL
               AND lease_expires_at < %s
             ORDER BY lease_expires_at, id
             FOR UPDATE SKIP LOCKED
             LIMIT %s
            """,
            [now, _STALE_SCAN_LIMIT],
        )
        turn_ids = [row[0] for row in cr.fetchall()]
        if not turn_ids:
            return
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        for turn in env["odoo.ai.turn"].browse(turn_ids).exists():
            if turn.state == "cancel_requested" or _control_cancel_requested_in_env(env, turn):
                _finalize_interrupted_answer(turn)
                turn.write(
                    {
                        "state": "cancelled",
                        "completed_at": now,
                        "lease_token": False,
                        "lease_expires_at": False,
                    }
                )
                event = ("cancelled", "Petición cancelada", None)
            elif turn.result_payload:
                turn.write(
                    {
                        "state": "completed",
                        "completed_at": turn.completed_at or now,
                        "lease_token": False,
                        "lease_expires_at": False,
                    }
                )
                event = ("completed", "Respuesta recuperada", None)
            elif turn.write_barrier:
                turn.write(
                    {
                        "state": "recovery_required",
                        "error_code": "worker_lost_after_write_barrier",
                        "completed_at": now,
                        "lease_token": False,
                        "lease_expires_at": False,
                    }
                )
                event = (
                    "recovery_required",
                    "La petición requiere revisión",
                    "worker_lost_after_write_barrier",
                )
            elif turn.attempt_count < turn.max_attempts:
                turn.write(
                    {
                        "state": "queued",
                        "queued_at": now,
                        "lease_token": False,
                        "lease_expires_at": False,
                        "error_code": False,
                    }
                )
                event = ("requeued", "Recuperando petición interrumpida", "worker_lost")
            else:
                turn.write(
                    {
                        "state": "failed",
                        "error_code": "worker_lost",
                        "completed_at": now,
                        "lease_token": False,
                        "lease_expires_at": False,
                    }
                )
                event = ("failed", "No se pudo recuperar la petición", "worker_lost")
            _append_event_in_env(
                env,
                turn,
                event[0],
                event[1],
                diagnostic_code=event[2],
            )
        cr.commit()
    _trigger_turn_crons(dbname)


def _cancellation_requested(dbname, turn_id, lease_token):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        return bool(
            turn
            and turn.lease_token == lease_token
            and (
                turn.state == "cancel_requested"
                or _control_cancel_requested_in_env(env, turn)
            )
        )


def _cancel_claimed_turn(dbname, turn_id, lease_token):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn or turn.lease_token != lease_token:
            return
        _finalize_interrupted_answer(turn)
        turn.write(
            {
                "state": "cancelled",
                "completed_at": fields.Datetime.now(),
                "lease_token": False,
                "lease_expires_at": False,
            }
        )
        cr.commit()
    _append_event(dbname, turn_id, "cancelled", "Petición cancelada")


def _control_cancel_requested_in_env(env, turn):
    control_model = env.get("odoo.ai.turn.control") if hasattr(env, "get") else None
    if control_model is None:
        try:
            control_model = env["odoo.ai.turn.control"]
        except KeyError:
            return False
    control = control_model.with_user(SUPERUSER_ID).search(
        [("turn_ref_id", "=", turn.id), ("turn_uuid", "=", turn.turn_uuid)],
        limit=1,
    )
    return bool(control and control.cancel_requested)


def _finalize_interrupted_answer(turn):
    finalize = getattr(turn, "_finalize_interrupted_answer", None)
    if callable(finalize):
        finalize()


def _append_event(
    dbname,
    turn_id,
    event_type,
    title,
    *,
    payload=None,
    diagnostic_code=None,
):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            return
        cr.execute("SELECT id FROM odoo_ai_turn WHERE id = %s FOR UPDATE", [turn_id])
        _append_event_in_env(
            env,
            turn,
            event_type,
            title,
            payload=payload,
            diagnostic_code=diagnostic_code,
        )
        cr.commit()


def _append_event_in_env(
    env,
    turn,
    event_type,
    title,
    *,
    payload=None,
    diagnostic_code=None,
):
    env["odoo.ai.turn.event"].append_for_turn(
        turn=turn,
        event_type=event_type,
        title=title,
        payload=payload,
        diagnostic_code=diagnostic_code,
    )


def _trigger_turn_crons(dbname):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        for xmlid in (
            "odoo_ai_assistant.ir_cron_assistant_turn_slot_1",
            "odoo_ai_assistant.ir_cron_assistant_turn_slot_2",
        ):
            env.ref(xmlid)._trigger()
        cr.commit()


def _runtime_error_code(error):
    code = getattr(error, "code", None)
    if isinstance(code, str) and _ERROR_CODE.fullmatch(code):
        return code
    if isinstance(error, AccessError):
        return "access_denied"
    return "runtime_unavailable"


def _validate_message(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= _MAX_MESSAGE
        or "\x00" in value
    ):
        raise ValidationError("Invalid Assistant message")


def _validate_json_bytes(value, *, maximum):
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ValidationError("Invalid Assistant payload") from None
    if len(encoded) > maximum:
        raise ValidationError("Assistant payload is too large")


def _request_fingerprint(
    *,
    uid,
    company_id,
    allowed_company_ids,
    message,
    screen,
    conversation_uuid,
):
    body = {
        "allowed_company_ids": list(allowed_company_ids),
        "company_id": company_id,
        "conversation_id": conversation_uuid,
        "message": message,
        "screen": screen,
        "uid": uid,
    }
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_client_request_id(value):
    if not isinstance(value, str) or re.fullmatch(_CLIENT_REQUEST_ID, value) is None:
        raise ValidationError("Invalid Assistant request id")
    return value


def _canonical_uuid(value):
    if not isinstance(value, str):
        raise ValidationError("Invalid Assistant turn id")
    try:
        parsed = str(UUID(value))
    except ValueError as error:
        raise ValidationError("Invalid Assistant turn id") from error
    if parsed != value:
        raise ValidationError("Invalid Assistant turn id")
    return parsed


def _new_uuid():
    from uuid import uuid4

    return uuid4()


def _title(message):
    normalized = " ".join(message.split())
    return normalized if len(normalized) <= 80 else normalized[:79].rstrip() + "…"
