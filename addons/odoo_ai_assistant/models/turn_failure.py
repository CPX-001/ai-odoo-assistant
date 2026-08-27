"""Structured terminal-failure persistence for Odoo-native Assistant turns."""

from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api, fields, models
from odoo.modules.registry import Registry

from ..runtime.agent.failure import (
    FailureEnvelope,
    FailureEnvelopeError,
    failure_envelope_payload,
    parse_failure_envelope,
)
from ..runtime.agent.terminal_failure import terminal_failure_envelope
from .turn_queue import (
    _NON_RETRYABLE_TURN_ERRORS,
    _append_event,
    _claim_next_turn,
    _execute_claimed_turn,
    _fail_claimed_turn,
    _recover_stale_turns,
    _runtime_error_code,
    _trigger_turn_crons,
)

_logger = logging.getLogger(__name__)
_TERMINAL_FAILURE_STATES = frozenset({"failed", "recovery_required"})


class AssistantTurnFailurePersistence(models.Model):
    _inherit = "odoo.ai.turn"

    failure_payload = fields.Json(readonly=True)

    def write(self, vals):
        """Keep terminal failure payloads validated and aligned with queue state."""

        if not isinstance(vals, dict):
            return super().write(vals)
        if len(self) > 1 and _needs_per_record_projection(vals):
            for record in self:
                record.write(dict(vals))
            return True
        if len(self) > 1:
            return super().write(dict(vals))

        values = dict(vals)
        current_state = self.state if self else None
        target_state = values.get("state", current_state)
        current_error = self.error_code if self else None
        target_error = values.get("error_code", current_error)

        if values.get("state") == "queued" or values.get("error_code") is False:
            values["failure_payload"] = False
        elif "failure_payload" in values and values["failure_payload"]:
            failure = parse_failure_envelope(values["failure_payload"])
            if target_state not in _TERMINAL_FAILURE_STATES:
                raise FailureEnvelopeError()
            if isinstance(target_error, str) and failure.code != target_error:
                raise FailureEnvelopeError()
            values["failure_payload"] = failure_envelope_payload(failure)
        elif (
            target_state in _TERMINAL_FAILURE_STATES
            and isinstance(target_error, str)
            and target_error
            and (
                values.get("state") in _TERMINAL_FAILURE_STATES
                or "error_code" in values
                or not self.failure_payload
            )
        ):
            write_barrier = values.get(
                "write_barrier",
                bool(self.write_barrier) if self else False,
            )
            failure = terminal_failure_envelope(
                None,
                error_code=target_error,
                write_barrier=bool(write_barrier),
            )
            values["failure_payload"] = failure_envelope_payload(failure)

        return super().write(values)

    def browser_status(self, *, after_sequence=0):
        self.ensure_one()
        status = super().browser_status(after_sequence=after_sequence)
        status["failure"] = _browser_failure_payload(
            self.failure_payload,
            expected_code=self.error_code or None,
        )
        return status

    @api.model
    def _cron_run_turn_slot(self):
        """Run one turn while preserving a structured terminal provider failure."""

        dbname = self.env.cr.dbname
        _recover_stale_turns(dbname)
        claimed = _claim_next_turn(dbname)
        if not claimed:
            return
        turn_id, lease_token = claimed
        try:
            _execute_claimed_turn(dbname, turn_id, lease_token)
        except Exception as error:  # noqa: BLE001 - queue boundary stays sanitized
            code = _runtime_error_code(error)
            _logger.exception("Embedded Assistant turn %s crashed: %s", turn_id, code)
            if isinstance(getattr(error, "failure", None), FailureEnvelope):
                _fail_claimed_turn_with_failure(
                    dbname,
                    turn_id,
                    lease_token,
                    error,
                    code,
                )
            else:
                # Keep the original queue/retry state machine for non-provider failures. The
                # model write overlay adds a bounded fallback envelope to terminal transitions.
                _fail_claimed_turn(dbname, turn_id, lease_token, code)


def _needs_per_record_projection(vals):
    return bool(
        vals.get("state") in _TERMINAL_FAILURE_STATES
        or vals.get("state") == "queued"
        or "failure_payload" in vals
        or vals.get("error_code") is False
    )


def _browser_failure_payload(raw, *, expected_code):
    if not isinstance(raw, dict):
        return None
    try:
        failure = parse_failure_envelope(raw)
    except FailureEnvelopeError:
        return None
    if expected_code is not None and failure.code != expected_code:
        return None
    return failure_envelope_payload(failure)


def _fail_claimed_turn_with_failure(
    dbname,
    turn_id,
    lease_token,
    error,
    error_code,
):
    """Preserve a carried provider envelope without changing queue retry semantics."""

    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn or turn.lease_token != lease_token:
            return

        if turn.state == "cancel_requested":
            turn.write(
                {
                    "state": "cancelled",
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                    "failure_payload": False,
                }
            )
            cr.commit()
            _append_event(dbname, turn_id, "cancelled", "Petición cancelada")
            return

        retryable = error_code not in _NON_RETRYABLE_TURN_ERRORS
        if retryable and not turn.write_barrier and turn.attempt_count < turn.max_attempts:
            turn.write(
                {
                    "state": "queued",
                    "queued_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                    "error_code": False,
                    "failure_payload": False,
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
        failure = terminal_failure_envelope(
            error,
            error_code=error_code,
            write_barrier=bool(turn.write_barrier),
        )
        turn.write(
            {
                "state": target_state,
                "error_code": error_code,
                "failure_payload": failure_envelope_payload(failure),
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
