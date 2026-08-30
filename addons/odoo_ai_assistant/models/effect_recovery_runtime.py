"""Durable recovery-unit execution overlay for Phase 6 EffectPlans."""

from __future__ import annotations

from odoo import SUPERUSER_ID, models

from ..runtime.agent import CapabilityPlanError
from ..runtime.agent.turn_effect_boundary import acquire_turn_effect_lock
from ..runtime.agent.working_transcript import (
    WorkingTranscriptError,
    transcript_payload,
)
from ..runtime.capabilities import CapabilityError
from .effect_journal import EffectJournalError
from .embedded_runtime import EmbeddedRuntimeError, _commit_plan_barrier
from .embedded_runtime_host_loop import (
    _append_verified_effect_receipt,
    _ensure_turn_control_current,
)


class EmbeddedAssistantEffectRecoveryRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    async def _execute_plan(
        self,
        turn,
        *,
        lease_token,
        envelope,
        plans,
        policy,
        registry,
        context,
        executor,
        working_items=None,
    ):
        """Execute host-owned recovery units and preserve durable certainty between them."""

        if working_items is None:
            try:
                working_items = turn._working_items_from_turn(turn)
            except WorkingTranscriptError as error:
                raise EmbeddedRuntimeError(error.code) from error

        working_payload = transcript_payload(working_items)
        journal = self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)

        def recovery_checkpoint(phase, plan_snapshot, unit, is_last):
            del is_last
            if phase not in {"before_unit", "after_unit"}:
                raise EmbeddedRuntimeError("capability_plan_recovery_checkpoint_invalid")
            if not isinstance(plan_snapshot, dict) or not isinstance(unit, dict):
                raise EmbeddedRuntimeError("capability_plan_recovery_checkpoint_invalid")

            current = dict(envelope)
            current["plan"] = plan_snapshot
            technical = turn.with_user(SUPERUSER_ID).exists()
            technical.invalidate_recordset(["state", "lease_token", "write_barrier"])
            if (
                not technical
                or technical.state != "running"
                or technical.lease_token != lease_token
            ):
                raise EmbeddedRuntimeError("agent_turn_lease_lost")

            if phase == "before_unit":
                # Each checkpoint commit releases the transaction-scoped lock, so every next unit
                # reacquires it before the final stop/redirect check and before effect execution.
                acquire_turn_effect_lock(turn.env.cr, turn.turn_uuid)
                _ensure_turn_control_current(turn)
                journal._sync_plan(turn, plan_snapshot)
                if not technical.write_barrier:
                    _commit_plan_barrier(
                        turn,
                        lease_token,
                        current,
                        working_items_payload=working_payload,
                    )
                    return
                technical.write(
                    {
                        "capability_plan_payload": current,
                        "working_items_payload": working_payload,
                    }
                )
                technical.env.cr.commit()
                return

            # A non-final completed unit becomes a durable recovery boundary. The following unit
            # will therefore never be blindly replayed after a later failure.
            if not technical.write_barrier:
                raise EmbeddedRuntimeError("capability_plan_barrier_missing")
            journal._sync_plan(turn, plan_snapshot)
            technical.write(
                {
                    "capability_plan_payload": current,
                    "working_items_payload": working_payload,
                }
            )
            technical.env.cr.commit()

        try:
            executed = await plans.execute(
                envelope["plan"],
                human_approved=bool(envelope["human_approved"]),
                recovery_checkpoint=recovery_checkpoint,
            )
        except (CapabilityPlanError, CapabilityError, EffectJournalError) as error:
            raise EmbeddedRuntimeError(error.code) from error

        completed = dict(envelope)
        completed["plan"] = executed.payload
        receipt_items = _append_verified_effect_receipt(working_items, executed.payload)
        try:
            journal._sync_plan(turn, executed.payload)
        except EffectJournalError as error:
            raise EmbeddedRuntimeError(error.code) from error
        turn.with_user(SUPERUSER_ID).write(
            {
                "capability_plan_payload": completed,
                "working_items_payload": transcript_payload(receipt_items),
            }
        )
        return await self._continue_after_effect(
            turn,
            lease_token=lease_token,
            completed=completed,
            policy=policy,
            registry=registry,
            context=context,
            executor=executor,
            working_items=receipt_items,
        )

    def _plan_response(self, turn, envelope, policy, *, completed=False):
        """Expose recovery shape without leaking journal snapshots or inventing atomicity."""

        response = super()._plan_response(turn, envelope, policy, completed=completed)
        source_plan = envelope.get("plan") if isinstance(envelope, dict) else None
        browser_plan = response.get("plan") if isinstance(response, dict) else None
        if not isinstance(source_plan, dict) or not isinstance(browser_plan, dict):
            return response
        units = source_plan.get("recovery_units")
        if not isinstance(units, list) or not units:
            return response
        modes = [unit.get("mode") for unit in units if isinstance(unit, dict)]
        if len(modes) != len(units) or any(
            mode not in {"odoo_atomic", "segmented", "external"} for mode in modes
        ):
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        metadata = dict(browser_plan.get("metadata") or {})
        metadata.update(
            {
                "is_atomic": len(units) == 1 and modes[0] == "odoo_atomic",
                "recovery_unit_count": len(units),
                "has_segmented_effects": "segmented" in modes,
                "has_external_effect": (
                    metadata.get("has_external_effect") is True or "external" in modes
                ),
            }
        )
        response["plan"] = {**browser_plan, "metadata": metadata}
        return response
