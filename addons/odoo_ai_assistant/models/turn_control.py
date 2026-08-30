"""Responsive stop/redirect controls and safe compensating actions for Assistant turns.

Interactive control is intentionally stored outside ``odoo.ai.turn``. A running worker may hold the
turn row while Codex is reasoning or while a business transaction is open; browser control must not
wait on that lock. The independent control row is Odoo-owned, bounded, user-bound and carries no
business authority. Effect compensation remains an explicit host-only capability lifecycle.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry

from ..runtime.agent.compensation import (
    CapabilityCompensationError,
    CapabilityCompensationService,
    plan_is_compensatable,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)
from .chat_policy import resolve_capability_policy

_MAX_INTERVENTIONS = 16
_MAX_INTERVENTION_CHARS = 4_000
_MAX_INTERVENTION_BYTES = 24 * 1024
_MAX_INTERRUPTED_ANSWER = 16 * 1024
_MAX_ATTEMPTS_WITH_REDIRECTS = 19
_REVERSION_STATES = {"none", "available", "unavailable", "completed"}


class TurnControlError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssistantTurnControlState(models.Model):
    _name = "odoo.ai.turn.control"
    _description = "Odoo AI Assistant Independent Turn Control"
    _log_access = False
    _order = "turn_ref_id"

    # Deliberately no FK to odoo.ai.turn: browser controls must never wait on a worker-held turn
    # row merely to request stop/redirect. The copied binding is validated on every host read.
    turn_ref_id = fields.Integer(required=True, readonly=True, index=True)
    turn_uuid = fields.Char(required=True, readonly=True, index=True, size=64)
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    intervention_sequence = fields.Integer(required=True, readonly=True, default=0)
    applied_sequence = fields.Integer(required=True, readonly=True, default=0)
    intervention_payload = fields.Json(readonly=True, copy=False)
    cancel_requested = fields.Boolean(required=True, readonly=True, default=False, index=True)
    cancel_requested_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "turn_control_ref_unique",
            "unique(turn_ref_id)",
            "Assistant turn control binding must be unique.",
        ),
        (
            "turn_control_sequence_valid",
            "CHECK(intervention_sequence >= 0 AND applied_sequence >= 0 AND applied_sequence <= intervention_sequence)",
            "Assistant turn control sequence is invalid.",
        ),
    ]


class AssistantTurnControl(models.Model):
    _inherit = "odoo.ai.turn"

    reversion_state = fields.Selection(
        [
            ("none", "Not applicable"),
            ("available", "Available"),
            ("unavailable", "Unavailable"),
            ("completed", "Completed"),
        ],
        required=True,
        readonly=True,
        default="none",
        index=True,
    )
    reversion_payload = fields.Json(readonly=True, copy=False)
    reverted_at = fields.Datetime(readonly=True)

    @api.model
    def redirect_for_current_user(self, turn_uuid, message):
        """Append one correction to the same queued/running/approval turn."""

        normalized = _validated_intervention(message)
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

        resume_after_sequence = _last_live_sequence(self.env, turn)
        control = _control_for_turn(self.env, turn, create=True)
        interventions = _validated_intervention_payload(
            control.intervention_payload or [],
            expected_sequence=int(control.intervention_sequence or 0),
        )
        if len(interventions) >= _MAX_INTERVENTIONS:
            raise TurnControlError("turn_redirect_limit_exceeded")
        sequence = int(control.intervention_sequence or 0) + 1
        user_message = self.env["odoo.ai.message"].create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "user",
                "content": normalized,
                "internal_workflow": "AGENT_REDIRECT",
            }
        )
        interventions.append(
            {
                "sequence": sequence,
                "message": normalized,
                "message_id": user_message.id,
            }
        )
        _bounded_interventions(interventions)
        control.write(
            {
                "intervention_payload": interventions,
                "intervention_sequence": sequence,
            }
        )
        if turn.conversation_id:
            turn.conversation_id.write({"last_message_at": fields.Datetime.now()})

        previous_state = turn.state
        if previous_state == "awaiting_confirmation":
            # The user's new instruction supersedes the pending approval. No effect has crossed the
            # write barrier, so the same turn is safely reset to reasoning and retains its UUID.
            next_max_attempts = min(
                _MAX_ATTEMPTS_WITH_REDIRECTS,
                max(int(turn.max_attempts), int(turn.attempt_count) + 2),
            )
            turn.with_user(SUPERUSER_ID).write(
                {
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
            )
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="approval.rejected",
                title="Plan sustituido por una nueva indicación",
                payload={"redirect_sequence": sequence},
            )
        elif previous_state == "queued":
            # No worker owns the row yet, so a historical audit event is cheap. While running we
            # deliberately avoid touching the turn row; the independent control row is the signal.
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="redirect.requested",
                title="Nueva indicación recibida",
                payload={"redirect_sequence": sequence},
            )

        if previous_state in {"queued", "awaiting_confirmation"}:
            self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_1")._trigger()
            self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_2")._trigger()
        return {
            "ok": True,
            "turn_id": turn.turn_uuid,
            "conversation_id": turn.conversation_id.conversation_uuid,
            "state": "queued" if previous_state == "awaiting_confirmation" else previous_state,
            "sequence": sequence,
            "resume_after_sequence": resume_after_sequence,
            "message": user_message._history_view(),
        }

    @api.model
    def runtime_control_snapshot(self, turn_uuid):
        """Read current cancellation/redirect state from an independent fresh cursor."""

        canonical = _canonical_uuid(turn_uuid)
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            turn = env["odoo.ai.turn"].search(
                [("turn_uuid", "=", canonical), ("user_id", "=", self.env.uid)],
                limit=1,
            )
            if not turn:
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
            interventions = _validated_intervention_payload(
                control.intervention_payload or [],
                expected_sequence=int(control.intervention_sequence or 0),
            )
            return {
                "cancel_requested": bool(control.cancel_requested),
                "sequence": int(control.intervention_sequence or 0),
                "applied_sequence": int(control.applied_sequence or 0),
                "interventions": [
                    {"sequence": item["sequence"], "message": item["message"]}
                    for item in interventions
                ],
            }

    @api.model
    def mark_runtime_control_applied(self, turn_uuid, sequence):
        """Record which redirect sequence produced the provider decision being returned."""

        canonical = _canonical_uuid(turn_uuid)
        if type(sequence) is not int or sequence < 0:
            raise TurnControlError("agent_turn_control_invalid")
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            turn = env["odoo.ai.turn"].search(
                [("turn_uuid", "=", canonical), ("user_id", "=", self.env.uid)],
                limit=1,
            )
            if not turn:
                raise TurnControlError("agent_turn_control_invalid")
            control = env["odoo.ai.turn.control"].search(
                [("turn_ref_id", "=", turn.id), ("turn_uuid", "=", turn.turn_uuid)],
                limit=1,
            )
            if not control:
                if sequence == 0:
                    return True
                raise TurnControlError("agent_turn_control_invalid")
            current = int(control.intervention_sequence or 0)
            if sequence > current:
                raise TurnControlError("agent_turn_control_invalid")
            applied = max(int(control.applied_sequence or 0), sequence)
            if applied != control.applied_sequence:
                control.write({"applied_sequence": applied})
                cr.commit()
            return True

    @api.model
    def cancel_for_current_user(self, turn_uuid):
        turn = self._owned_turn(turn_uuid)
        turn.invalidate_recordset(["state", "write_barrier"])
        if turn.state in {"completed", "failed", "cancelled", "recovery_required"}:
            return turn.browser_status(after_sequence=0)
        if turn.state == "queued":
            return super().cancel_for_current_user(turn_uuid)
        if turn.state == "awaiting_confirmation":
            # No worker owns an approval wait. Supersede the proposal and terminalize immediately.
            envelope = turn.capability_plan_payload
            if isinstance(envelope, dict) and isinstance(envelope.get("plan"), dict):
                plan = dict(envelope["plan"])
                plan["state"] = "rejected"
                envelope = {**envelope, "plan": plan}
            turn.with_user(SUPERUSER_ID).write(
                {
                    "state": "cancelled",
                    "capability_plan_payload": envelope or False,
                    "cancel_requested_at": fields.Datetime.now(),
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            turn._finalize_interrupted_answer()
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="cancelled",
                title="Petición cancelada",
            )
            return turn.browser_status(after_sequence=0)

        # Running cancellation must not update the turn row: that row can be held by the worker.
        control = _control_for_turn(self.env, turn, create=True)
        if not control.cancel_requested:
            control.write(
                {
                    "cancel_requested": True,
                    "cancel_requested_at": fields.Datetime.now(),
                }
            )
        result = turn.browser_status(after_sequence=0)
        result["state"] = "cancel_requested"
        result["answer"] = _interrupted_content(self.env, turn)
        return result

    def browser_status(self, *, after_sequence=0):
        self.ensure_one()
        result = super().browser_status(after_sequence=after_sequence)
        if self.state == "cancelled" and isinstance(self.result_payload, dict):
            result["response"] = dict(self.result_payload)
        return result

    def _finalize_interrupted_answer(self):
        """Persist the visible interrupted Assistant message once the worker owns the turn row."""

        self.ensure_one()
        if self.assistant_message_id or not self.conversation_id:
            return
        content = _interrupted_content(self.env, self)
        message = self.env["odoo.ai.message"].with_user(SUPERUSER_ID).create(
            {
                "conversation_id": self.conversation_id.id,
                "role": "assistant",
                "content": content,
                "internal_workflow": "AGENT_INTERRUPTED",
            }
        )
        values = {"assistant_message_id": message.id}
        if isinstance(self.result_payload, dict):
            response = dict(self.result_payload)
            response["answer"] = content
            values["result_payload"] = response
        self.with_user(SUPERUSER_ID).write(values)
        self.conversation_id.with_user(SUPERUSER_ID).write(
            {"last_message_at": fields.Datetime.now()}
        )

    @api.model
    def revert_for_current_user(self, turn_uuid):
        """Run explicit host compensators for one completed verified effect plan."""

        turn = self._owned_turn(turn_uuid)
        self.env.cr.execute("SELECT id FROM odoo_ai_turn WHERE id = %s FOR UPDATE", [turn.id])
        turn.invalidate_recordset(
            [
                "state",
                "write_barrier",
                "capability_plan_payload",
                "result_payload",
                "reversion_state",
            ]
        )
        if turn.state not in {"completed", "cancelled"}:
            raise TurnControlError("turn_reversion_not_ready")
        if not turn.write_barrier or turn.reversion_state != "available":
            raise TurnControlError("turn_reversion_unavailable")
        envelope = turn.capability_plan_payload
        plan = envelope.get("plan") if isinstance(envelope, dict) else None
        if not isinstance(plan, dict) or plan.get("state") != "completed":
            raise TurnControlError("turn_reversion_unavailable")

        policy_snapshot = resolve_capability_policy(turn.policy_payload or {})
        registry = discover_capabilities()
        resolver = CapabilityConfigResolver.from_env(self.env)
        enablement = resolver.enablement_overrides(registry.definitions)

        def event_sink(event_type, title, payload):
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type=event_type,
                title=title,
                payload=dict(payload),
            )

        context = CapabilityContext(
            env=self.env,
            turn_id=turn.turn_uuid,
            conversation_id=turn.conversation_id.conversation_uuid if turn.conversation_id else None,
            screen=turn.screen_payload or {},
            event_sink=event_sink,
            metadata={
                "capability_enabled": enablement,
                "capability_policy": policy_snapshot,
            },
        )
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=resolver,
        )
        compensation = CapabilityCompensationService(
            registry=registry,
            context=context,
            executor=executor,
        )
        try:
            with self.env.cr.savepoint():
                execution = asyncio.run(compensation.compensate(plan))
        except CapabilityCompensationError as error:
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type="reversion.failed",
                title="No se pudieron revertir los cambios",
                diagnostic_code=error.code,
            )
            raise TurnControlError(error.code) from error

        response = _response_with_reversion_state(turn.result_payload, "completed")
        summary = {
            "verified": True,
            "step_count": len(execution.results),
            "operations": [result.data.get("operation") for result in execution.results],
        }
        technical = turn.with_user(SUPERUSER_ID)
        technical.write(
            {
                "reversion_state": "completed",
                "reversion_payload": summary,
                "reverted_at": fields.Datetime.now(),
                "result_payload": response,
            }
        )
        assistant_message = self.env["odoo.ai.message"].with_user(SUPERUSER_ID).create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "assistant",
                "content": "He revertido y verificado los cambios de esta operación.",
                "internal_workflow": "AGENT_REVERSION",
            }
        )
        if turn.conversation_id:
            turn.conversation_id.with_user(SUPERUSER_ID).write(
                {"last_message_at": fields.Datetime.now()}
            )
        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=technical,
            event_type="reversion.completed",
            title="Cambios revertidos",
            payload={"step_count": len(execution.results)},
        )
        return {
            "ok": True,
            "turn_id": turn.turn_uuid,
            "conversation_id": turn.conversation_id.conversation_uuid,
            "state": "reverted",
            "response": response,
            "message": assistant_message._history_view(),
        }

    def unlink(self):
        turn_ids = self.ids
        result = super().unlink()
        if turn_ids:
            self.env["odoo.ai.turn.control"].with_user(SUPERUSER_ID).search(
                [("turn_ref_id", "in", turn_ids)]
            ).unlink()
        return result


class EmbeddedAssistantTurnControlRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    def _conversation_summary(self, turn):
        if not turn.conversation_id:
            return ""
        control = _control_for_turn(self.env, turn, create=False)
        interventions = _validated_intervention_payload(
            control.intervention_payload or [] if control else [],
            expected_sequence=int(control.intervention_sequence or 0) if control else 0,
        )
        excluded = [turn.user_message_id.id] if turn.user_message_id else []
        excluded.extend(item["message_id"] for item in interventions)
        domain = [
            ("conversation_id", "=", turn.conversation_id.id),
            ("user_id", "=", self.env.uid),
        ]
        if excluded:
            domain.append(("id", "not in", excluded))
        newest = self.env["odoo.ai.message"].search(
            domain,
            limit=8,
            order="create_date desc, id desc",
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

    def _plan_response(self, turn, envelope, policy, *, completed=False):
        reversion_state = turn.reversion_state or "none"
        plan = envelope.get("plan") if isinstance(envelope, dict) else None
        if completed and isinstance(plan, dict) and plan.get("state") == "completed":
            reversion_state = self._plan_reversion_state(turn, plan, policy)
            turn.with_user(SUPERUSER_ID).write({"reversion_state": reversion_state})
        response = super()._plan_response(turn, envelope, policy, completed=completed)
        response["plan"] = _plan_with_reversion_state(response.get("plan"), reversion_state)
        return response

    def _plan_reversion_state(self, turn, plan, policy):
        registry = discover_capabilities()
        resolver = CapabilityConfigResolver.from_env(self.env)
        context = CapabilityContext(
            env=self.env,
            turn_id=turn.turn_uuid,
            conversation_id=turn.conversation_id.conversation_uuid if turn.conversation_id else None,
            screen=turn.screen_payload or {},
            metadata={
                "capability_enabled": resolver.enablement_overrides(registry.definitions),
                "capability_policy": policy,
            },
        )
        return "available" if plan_is_compensatable(registry, context, plan) else "unavailable"


def _control_for_turn(env, turn, *, create):
    control_model = env["odoo.ai.turn.control"].with_user(SUPERUSER_ID)
    control = control_model.search(
        [("turn_ref_id", "=", turn.id), ("turn_uuid", "=", turn.turn_uuid)],
        limit=1,
    )
    if control or not create:
        return control
    return control_model.create(
        {
            "turn_ref_id": turn.id,
            "turn_uuid": turn.turn_uuid,
            "user_id": turn.user_id.id,
            "company_id": turn.company_id.id,
            "intervention_sequence": 0,
            "applied_sequence": 0,
            "intervention_payload": [],
            "cancel_requested": False,
        }
    )


def _plan_with_reversion_state(plan, state):
    if not isinstance(plan, dict):
        return plan
    normalized = state if state in _REVERSION_STATES else "none"
    metadata = dict(plan.get("metadata") or {})
    metadata["revertible"] = normalized == "available"
    metadata["reversion_state"] = normalized
    return {**plan, "metadata": metadata}


def _response_with_reversion_state(response, state):
    if not isinstance(response, dict) or not isinstance(response.get("plan"), dict):
        raise TurnControlError("turn_reversion_response_invalid")
    return {**response, "plan": _plan_with_reversion_state(response["plan"], state)}


def _interrupted_content(env, turn):
    rows = env["odoo.ai.turn.live.event"].with_user(SUPERUSER_ID).search(
        [
            ("turn_ref_id", "=", turn.id),
            ("turn_uuid", "=", turn.turn_uuid),
            ("channel", "=", "answer"),
        ],
        order="sequence",
        limit=1024,
    )
    partial = "".join(row.answer_delta or "" for row in rows)[:_MAX_INTERRUPTED_ANSWER].rstrip()
    return f"{partial}\n\n— Interrumpido" if partial else "Interrumpido."


def _last_live_sequence(env, turn):
    last = env["odoo.ai.turn.live.event"].with_user(SUPERUSER_ID).search(
        [("turn_ref_id", "=", turn.id), ("turn_uuid", "=", turn.turn_uuid)],
        order="sequence desc",
        limit=1,
    )
    return int(last.sequence or 0) if last else 0


def _validated_intervention(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= _MAX_INTERVENTION_CHARS
        or "\x00" in value
    ):
        raise ValidationError("Invalid Assistant redirect")
    return value.strip()


def _validated_intervention_payload(value, *, expected_sequence):
    if not isinstance(value, list) or len(value) > _MAX_INTERVENTIONS:
        raise TurnControlError("agent_turn_control_invalid")
    normalized = []
    previous = 0
    for item in value:
        if not isinstance(item, dict) or set(item) != {"message", "message_id", "sequence"}:
            raise TurnControlError("agent_turn_control_invalid")
        sequence = item.get("sequence")
        message = item.get("message")
        message_id = item.get("message_id")
        if (
            type(sequence) is not int
            or sequence <= previous
            or not isinstance(message, str)
            or not 1 <= len(message.strip()) <= _MAX_INTERVENTION_CHARS
            or "\x00" in message
            or type(message_id) is not int
            or message_id <= 0
        ):
            raise TurnControlError("agent_turn_control_invalid")
        previous = sequence
        normalized.append(
            {"sequence": sequence, "message": message, "message_id": message_id}
        )
    if previous != expected_sequence or (not normalized and expected_sequence != 0):
        raise TurnControlError("agent_turn_control_invalid")
    _bounded_interventions(normalized)
    return normalized


def _bounded_interventions(interventions):
    try:
        raw = json.dumps(
            interventions,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise TurnControlError("agent_turn_control_invalid") from None
    if len(raw) > _MAX_INTERVENTION_BYTES:
        raise TurnControlError("turn_redirect_budget_exceeded")


def _canonical_uuid(value):
    if not isinstance(value, str):
        raise TurnControlError("agent_turn_control_invalid")
    try:
        parsed = str(UUID(value))
    except ValueError as error:
        raise TurnControlError("agent_turn_control_invalid") from error
    if parsed != value:
        raise TurnControlError("agent_turn_control_invalid")
    return parsed
