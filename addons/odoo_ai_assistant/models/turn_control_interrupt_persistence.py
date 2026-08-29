"""Persist visible interrupted prose without blocking on the active turn row."""

from odoo import SUPERUSER_ID, fields, models

from .turn_control import _control_for_turn


def _interrupted_tag(turn):
    return f"AGENT_INTERRUPTED:{turn.turn_uuid}"


class AssistantTurnInterruptedPersistence(models.Model):
    _inherit = "odoo.ai.turn"

    def _persist_independent_interrupted_message(self, content):
        self.ensure_one()
        if not self.conversation_id or not isinstance(content, str) or not content:
            return self.env["odoo.ai.message"].browse()
        tag = _interrupted_tag(self)
        message_model = self.env["odoo.ai.message"].with_user(SUPERUSER_ID)
        existing = message_model.search(
            [
                ("conversation_id", "=", self.conversation_id.id),
                ("internal_workflow", "=", tag),
            ],
            limit=1,
        )
        if existing:
            return existing
        # This writes only the message table. In particular it never updates the active turn row,
        # so a browser Stop is not serialized behind the worker's business transaction.
        return message_model.create(
            {
                "conversation_id": self.conversation_id.id,
                "role": "assistant",
                "content": content,
                "internal_workflow": tag,
            }
        )

    def _finalize_interrupted_answer(self):
        self.ensure_one()
        if self.assistant_message_id:
            return
        existing = (
            self.env["odoo.ai.message"].with_user(SUPERUSER_ID).search(
                [
                    ("conversation_id", "=", self.conversation_id.id),
                    ("internal_workflow", "=", _interrupted_tag(self)),
                ],
                limit=1,
            )
            if self.conversation_id
            else self.env["odoo.ai.message"].browse()
        )
        if not existing:
            return super()._finalize_interrupted_answer()
        self.with_user(SUPERUSER_ID).write({"assistant_message_id": existing.id})
        self.conversation_id.with_user(SUPERUSER_ID).write(
            {"last_message_at": fields.Datetime.now()}
        )

    def cancel_for_current_user(self, turn_uuid):
        turn = self._owned_turn(turn_uuid)
        # Set the independent flag before the legacy queued-state update. If a scheduler races the
        # request and claims the turn between our read and that update, the worker still observes
        # the durable cancellation flag and interrupts instead of executing the user's stale work.
        if turn.state == "queued":
            control = _control_for_turn(self.env, turn, create=True)
            if not control.cancel_requested:
                control.write(
                    {
                        "cancel_requested": True,
                        "cancel_requested_at": fields.Datetime.now(),
                    }
                )
        was_running = turn.state in {"running", "cancel_requested"}
        response = super().cancel_for_current_user(turn_uuid)
        if was_running and response.get("state") in {"cancel_requested", "cancelled"}:
            answer = response.get("answer")
            if isinstance(answer, str) and answer:
                message = turn._persist_independent_interrupted_message(answer)
                if message:
                    response["message"] = message._history_view()
        return response
