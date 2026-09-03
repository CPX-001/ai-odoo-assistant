"""Durable ordered user interventions for one persisted Assistant turn.

The provider process is deliberately not the source of truth for corrections.  Each correction is
stored in Odoo first, bound to the current user/company/conversation/turn and assigned a monotonic
sequence.  The independent table has no FK to the worker-owned turn row so a live correction does
not wait on a long-running business transaction merely to become durable.
"""

from __future__ import annotations

import json
import re

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry

from .turn_control import (
    TurnControlError,
    _control_for_turn,
    _last_live_sequence,
    _validated_intervention,
    _validated_intervention_payload,
)

_CLIENT_INTERVENTION_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_MAX_INTERVENTIONS = 16
_MAX_INTERVENTION_BYTES = 24 * 1024
_MAX_ATTEMPTS_WITH_REDIRECTS = 19


class AssistantTurnIntervention(models.Model):
    _name = "odoo.ai.turn.intervention"
    _description = "Odoo AI Assistant Durable Turn Intervention"
    _log_access = False
    _order = "turn_ref_id, sequence"

    # Integer copied bindings are intentional.  A worker may hold odoo.ai.turn while Codex or a
    # business transaction is active; an FK insert would unnecessarily couple browser control to
    # that row lock.  Every reader revalidates the copied UUID/user/company/conversation binding.
    turn_ref_id = fields.Integer(required=True, readonly=True, index=True)
    turn_uuid = fields.Char(required=True, readonly=True, index=True, size=64)
    conversation_ref_id = fields.Integer(required=True, readonly=True, index=True)
    conversation_uuid = fields.Char(required=True, readonly=True, index=True, size=64)
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    sequence = fields.Integer(required=True, readonly=True, index=True)
    client_intervention_id = fields.Char(required=True, readonly=True, index=True, size=128)
    message = fields.Text(required=True, readonly=True)
    message_ref_id = fields.Integer(required=True, readonly=True)
    state = fields.Selection(
        [("pending", "Pending"), ("applied", "Applied"), ("superseded", "Superseded")],
        required=True,
        readonly=True,
        default="pending",
        index=True,
    )
    applied_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "turn_intervention_client_unique",
            "unique(turn_ref_id, client_intervention_id)",
            "Assistant intervention id must be unique per turn.",
        ),
        (
            "turn_intervention_sequence_unique",
            "unique(turn_ref_id, sequence)",
            "Assistant intervention sequence must be unique per turn.",
        ),
        (
            "turn_intervention_sequence_positive",
            "CHECK(sequence > 0)",
            "Assistant intervention sequence must be positive.",
        ),
    ]


class AssistantTurnInterventionControl(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def redirect_for_current_user(self, turn_uuid, message, client_intervention_id=None):
        normalized = _validated_intervention(message)
        client_id = _validated_client_intervention_id(client_intervention_id)
        turn = self._owned_turn(turn_uuid)
        turn.invalidate_recordset(
            [
                "state",
                "write_barrier",
                "attempt_count",
                "max_attempts",
                "capability_plan_payload",
            ]
        )
        if turn.write_barrier:
            raise TurnControlError("turn_effect_already_committed")
        if turn.state not in {"queued", "running", "awaiting_confirmation"}:
            raise TurnControlError("turn_not_redirectable")
        if not turn.conversation_id:
            raise TurnControlError("agent_turn_control_invalid")

        model = self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID)
        binding = _intervention_domain(turn)
        existing = model.search(binding + [("client_intervention_id", "=", client_id)], limit=1)
        if existing:
            if existing.message != normalized:
                raise TurnControlError("turn_intervention_id_conflict")
            return _intervention_response(
                self.env,
                turn,
                existing,
                state=turn.state,
                duplicate=True,
            )

        control = _control_for_turn(self.env, turn, create=True)
        legacy = _legacy_interventions(control)
        rows = model.search(binding, order="sequence")
        if len(legacy) + len(rows) >= _MAX_INTERVENTIONS:
            raise TurnControlError("turn_redirect_limit_exceeded")
        _validate_total_budget(legacy, rows, normalized)

        sequence = int(control.intervention_sequence or 0) + 1
        # Guard against a corrupt/copied binding before creating browser-visible history.
        if rows and rows[-1].sequence >= sequence:
            raise TurnControlError("agent_turn_control_invalid")
        resume_after_sequence = _last_live_sequence(self.env, turn)
        user_message = self.env["odoo.ai.message"].create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "user",
                "content": normalized,
                "internal_workflow": "AGENT_REDIRECT",
            }
        )
        intervention = model.create(
            {
                "turn_ref_id": turn.id,
                "turn_uuid": turn.turn_uuid,
                "conversation_ref_id": turn.conversation_id.id,
                "conversation_uuid": turn.conversation_id.conversation_uuid,
                "user_id": turn.user_id.id,
                "company_id": turn.company_id.id,
                "sequence": sequence,
                "client_intervention_id": client_id,
                "message": normalized,
                "message_ref_id": user_message.id,
                "state": "pending",
            }
        )
        control.write({"intervention_sequence": sequence})
        turn.conversation_id.write({"last_message_at": fields.Datetime.now()})

        previous_state = turn.state
        if previous_state == "awaiting_confirmation":
            envelope = turn.capability_plan_payload
            if isinstance(envelope, dict) and isinstance(envelope.get("plan"), dict):
                plan = dict(envelope["plan"])
                plan["state"] = "rejected"
                envelope = {**envelope, "plan": plan}
            # Record the explicit supersession before clearing executable state.
            self.env["odoo.ai.turn.event"].with_user(
                SUPERUSER_ID
            ).append_optional_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="approval.rejected",
                title="Plan sustituido por una nueva indicación",
                payload={
                    "redirect_sequence": sequence,
                    "client_intervention_id": client_id,
                },
            )
            next_max_attempts = min(
                _MAX_ATTEMPTS_WITH_REDIRECTS,
                max(int(turn.max_attempts), int(turn.attempt_count) + 2),
            )
            values = {
                "state": "queued",
                "queued_at": fields.Datetime.now(),
                "capability_plan_payload": False,
                "working_items_payload": False,
                "result_payload": False,
                "assistant_message_id": False,
                "error_code": False,
                "lease_token": False,
                "lease_expires_at": False,
                "completed_at": False,
                "max_attempts": next_max_attempts,
            }
            if "public_reference_payload" in turn._fields:
                values["public_reference_payload"] = False
            turn.with_user(SUPERUSER_ID).write(values)
        elif previous_state == "queued":
            self.env["odoo.ai.turn.event"].with_user(
                SUPERUSER_ID
            ).append_optional_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="redirect.requested",
                title="Nueva indicación recibida",
                payload={
                    "redirect_sequence": sequence,
                    "client_intervention_id": client_id,
                },
            )

        if previous_state in {"queued", "awaiting_confirmation"}:
            self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_1")._trigger()
            self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_2")._trigger()
        return _intervention_response(
            self.env,
            turn,
            intervention,
            state="queued" if previous_state == "awaiting_confirmation" else previous_state,
            duplicate=False,
            resume_after_sequence=resume_after_sequence,
        )

    @api.model
    def runtime_control_snapshot(self, turn_uuid):
        canonical = self._owned_turn(turn_uuid).turn_uuid
        uid = self.env.uid
        company_id = self.env.company.id
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            turn = env["odoo.ai.turn"].search(
                [
                    ("turn_uuid", "=", canonical),
                    ("user_id", "=", uid),
                    ("company_id", "=", company_id),
                ],
                limit=1,
            )
            if not turn or not turn.conversation_id:
                raise TurnControlError("agent_turn_control_invalid")
            control = env["odoo.ai.turn.control"].search(
                [("turn_ref_id", "=", turn.id), ("turn_uuid", "=", turn.turn_uuid)],
                limit=1,
            )
            if not control:
                return {
                    "cancel_requested": False,
                    "sequence": 0,
                    "applied_sequence": 0,
                    "interventions": [],
                }
            legacy = _legacy_interventions(control)
            rows = env["odoo.ai.turn.intervention"].search(
                _intervention_domain(turn), order="sequence"
            )
            interventions = [
                {"sequence": item["sequence"], "message": item["message"]}
                for item in legacy
            ]
            interventions.extend(
                {"sequence": row.sequence, "message": row.message} for row in rows
            )
            _validate_snapshot_sequence(
                interventions,
                expected_sequence=int(control.intervention_sequence or 0),
            )
            return {
                "cancel_requested": bool(control.cancel_requested),
                "sequence": int(control.intervention_sequence or 0),
                "applied_sequence": int(control.applied_sequence or 0),
                "interventions": interventions,
            }

    @api.model
    def mark_runtime_control_applied(self, turn_uuid, sequence):
        turn = self._owned_turn(turn_uuid)
        if type(sequence) is not int or sequence < 0:
            raise TurnControlError("agent_turn_control_invalid")
        uid = self.env.uid
        company_id = self.env.company.id
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            fresh = env["odoo.ai.turn"].search(
                [
                    ("id", "=", turn.id),
                    ("turn_uuid", "=", turn.turn_uuid),
                    ("user_id", "=", uid),
                    ("company_id", "=", company_id),
                ],
                limit=1,
            )
            if not fresh:
                raise TurnControlError("agent_turn_control_invalid")
            control = env["odoo.ai.turn.control"].search(
                [("turn_ref_id", "=", fresh.id), ("turn_uuid", "=", fresh.turn_uuid)], limit=1
            )
            if not control:
                if sequence == 0:
                    return True
                raise TurnControlError("agent_turn_control_invalid")
            current = int(control.intervention_sequence or 0)
            if sequence > current:
                raise TurnControlError("agent_turn_control_invalid")
            applied = max(int(control.applied_sequence or 0), sequence)
            if applied != int(control.applied_sequence or 0):
                control.write({"applied_sequence": applied})
                rows = env["odoo.ai.turn.intervention"].search(
                    _intervention_domain(fresh)
                    + [("sequence", "<=", applied), ("state", "=", "pending")]
                )
                if rows:
                    rows.write({"state": "applied", "applied_at": fields.Datetime.now()})
                cr.commit()
            return True


class EmbeddedAssistantTurnInterventionRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    def _conversation_summary(self, turn):
        if not turn.conversation_id:
            return ""
        excluded = [turn.user_message_id.id] if turn.user_message_id else []
        control = _control_for_turn(self.env, turn, create=False)
        if control:
            excluded.extend(
                item["message_id"] for item in _legacy_interventions(control)
            )
        rows = self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
            _intervention_domain(turn), order="sequence"
        )
        excluded.extend(row.message_ref_id for row in rows)
        domain = [
            ("conversation_id", "=", turn.conversation_id.id),
            ("user_id", "=", self.env.uid),
        ]
        if excluded:
            domain.append(("id", "not in", excluded))
        newest = self.env["odoo.ai.message"].search(
            domain, limit=8, order="create_date desc, id desc"
        )
        retained = []
        used = 0
        for item in newest:
            prefix = "User" if item.role == "user" else "Assistant"
            line = f"{prefix}: {item.content.strip()}"
            remaining = 8_000 - used - (1 if retained else 0)
            if remaining <= 0:
                break
            retained.append(line[:remaining])
            used += len(retained[-1]) + (1 if len(retained) > 1 else 0)
        return "\n".join(reversed(retained))


def _validated_client_intervention_id(value):
    if not isinstance(value, str) or _CLIENT_INTERVENTION_ID.fullmatch(value) is None:
        raise ValidationError("Invalid Assistant intervention id")
    return value


def _intervention_domain(turn):
    if not turn.conversation_id:
        return [("id", "=", 0)]
    return [
        ("turn_ref_id", "=", turn.id),
        ("turn_uuid", "=", turn.turn_uuid),
        ("conversation_ref_id", "=", turn.conversation_id.id),
        ("conversation_uuid", "=", turn.conversation_id.conversation_uuid),
        ("user_id", "=", turn.user_id.id),
        ("company_id", "=", turn.company_id.id),
    ]


def _legacy_interventions(control):
    if not control or not control.intervention_payload:
        return []
    return _validated_intervention_payload(
        control.intervention_payload,
        expected_sequence=min(
            int(control.intervention_sequence or 0),
            max(
                [
                    item.get("sequence", 0)
                    for item in control.intervention_payload
                    if isinstance(item, dict)
                ],
                default=0,
            ),
        ),
    )


def _validate_total_budget(legacy, rows, new_message):
    messages = [item["message"] for item in legacy]
    messages.extend(row.message for row in rows)
    messages.append(new_message)
    encoded = json.dumps(
        messages,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > _MAX_INTERVENTION_BYTES:
        raise TurnControlError("turn_redirect_budget_exceeded")


def _validate_snapshot_sequence(interventions, *, expected_sequence):
    previous = 0
    for item in interventions:
        if (
            not isinstance(item, dict)
            or set(item) != {"sequence", "message"}
            or type(item["sequence"]) is not int
            or item["sequence"] != previous + 1
            or not isinstance(item["message"], str)
        ):
            raise TurnControlError("agent_turn_control_invalid")
        previous = item["sequence"]
    if previous != expected_sequence:
        raise TurnControlError("agent_turn_control_invalid")


def _intervention_response(
    env,
    turn,
    intervention,
    *,
    state,
    duplicate,
    resume_after_sequence=None,
):
    message = env["odoo.ai.message"].with_user(SUPERUSER_ID).browse(intervention.message_ref_id).exists()
    if not message or message.conversation_id.id != turn.conversation_id.id:
        raise TurnControlError("agent_turn_control_invalid")
    return {
        "ok": True,
        "turn_id": turn.turn_uuid,
        "conversation_id": turn.conversation_id.conversation_uuid,
        "state": state,
        "sequence": intervention.sequence,
        "client_intervention_id": intervention.client_intervention_id,
        "duplicate": duplicate,
        "resume_after_sequence": (
            _last_live_sequence(env, turn)
            if resume_after_sequence is None
            else resume_after_sequence
        ),
        "message": message._history_view(),
    }
