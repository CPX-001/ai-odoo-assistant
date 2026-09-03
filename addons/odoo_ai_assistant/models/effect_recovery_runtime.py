"""Durable recovery-unit execution overlay for Phase 6 EffectPlans."""

from __future__ import annotations

from odoo import SUPERUSER_ID, models

from ..runtime.agent import (
    AgentTurnService,
    CapabilityPlanError,
    CapabilityPlanStepError,
    PlanningDecisionEngine,
)
from ..runtime.agent.interactive_codex import InteractiveCodexDecisionEngine
from ..runtime.agent.provider_failure import FailureNormalizingDecisionEngine
from ..runtime.agent.turn_effect_boundary import acquire_turn_effect_lock
from ..runtime.agent.working_transcript import (
    WorkingTranscriptError,
    append_working_item,
    transcript_payload,
)
from ..runtime.capabilities import CapabilityConfigResolver, CapabilityError
from .effect_journal import EffectJournalError
from .embedded_runtime import EmbeddedRuntimeError, _commit_plan_barrier
from .embedded_runtime_host_loop import (
    _append_verified_effect_receipt,
    _append_plan_prepared,
    _ensure_turn_control_current,
    _new_reasoning_activity_id,
    _with_assistant_extensions,
)
from .turn_working_transcript import persist_working_transcript


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
        except CapabilityPlanStepError as error:
            return await self._repair_recoverable_plan(
                turn,
                lease_token=lease_token,
                envelope=envelope,
                error=error,
                plans=plans,
                policy=policy,
                registry=registry,
                context=context,
                executor=executor,
                working_items=working_items,
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

    async def _repair_recoverable_plan(
        self,
        turn,
        *,
        lease_token,
        envelope,
        error,
        plans,
        policy,
        registry,
        context,
        executor,
        working_items,
    ):
        """Give a proven no-effect failure back to the model without expanding authority."""

        source_plan = envelope.get("plan") if isinstance(envelope, dict) else None
        units = source_plan.get("recovery_units") if isinstance(source_plan, dict) else None
        if not isinstance(units, list) or not units:
            raise EmbeddedRuntimeError(error.code) from error
        if error.phase == "execution" and (
            len(units) != 1 or units[0].get("mode") != "odoo_atomic"
        ):
            raise EmbeddedRuntimeError(error.code) from error
        max_replans = policy.get("max_replans", 0) if isinstance(policy, dict) else 0
        replan_count = sum(item.kind == "plan_execution_error" for item in working_items)

        if error.phase == "execution":
            # The plan barrier was committed before execution. Everything afterwards belongs to
            # the current Odoo transaction, so rollback is authoritative for this atomic unit.
            self.env.cr.rollback()
            self.env.invalidate_all()
            turn = self.env["odoo.ai.turn"].browse(turn.id).exists()
            turn.invalidate_recordset()
            _ensure_turn_control_current(turn)
            journal = self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)
            journal._mark_turn_failure(turn)
            if not journal._all_turn_effects_rolled_back(turn):
                raise EmbeddedRuntimeError(error.code) from error
        elif error.phase in {"prepare", "preflight"}:
            turn.invalidate_recordset(["write_barrier"])
            _ensure_turn_control_current(turn)
            if turn.write_barrier:
                raise EmbeddedRuntimeError(error.code) from error
        else:
            raise EmbeddedRuntimeError(error.code) from error

        repaired_items = append_working_item(
            working_items,
            "plan_execution_error",
            {
                "code": error.code,
                "step_id": error.step_id,
                "capability": error.capability,
                "phase": error.phase,
                "details": dict(error.details),
                "effect_state": "none",
                "rolled_back": error.phase == "execution",
                "replan": replan_count + 1,
            },
        )
        turn.with_user(SUPERUSER_ID).write(
            {
                "write_barrier": False,
                "capability_plan_payload": False,
                "working_items_payload": transcript_payload(repaired_items),
                "error_code": False,
                "failure_payload": False,
            }
        )
        self.env.cr.commit()

        dbname = self.env.cr.dbname

        def cancellation_requested():
            from .turn_queue import _cancellation_requested

            return _cancellation_requested(dbname, turn.id, lease_token)

        def persist(items):
            try:
                persist_working_transcript(turn, lease_token, items)
            except RuntimeError as persist_error:
                raise EmbeddedRuntimeError(str(persist_error)) from persist_error

        resolver = CapabilityConfigResolver.from_env(self.env)
        decision_engine = PlanningDecisionEngine(
            _with_assistant_extensions(
                self.env,
                FailureNormalizingDecisionEngine(
                    InteractiveCodexDecisionEngine(
                        self._codex_settings(turn),
                        cancellation_requested=cancellation_requested,
                    ),
                    component="codex",
                    effect_state="none",
                ),
                registry=registry,
                config=resolver,
            )
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=decision_engine,
            working_items=repaired_items,
            persist_working_items=persist,
            cancellation_requested=cancellation_requested,
            allow_plan_proposals=True,
        )
        if type(max_replans) is not int or replan_count >= max_replans:
            result = await service.finish_safely(error.code)
            return self._read_only_response(turn, result, policy)
        activity_id = _new_reasoning_activity_id()
        context.emit(
            "reasoning.started",
            "Corrigiendo ejecución",
            {"activity_id": activity_id, "replan": replan_count + 1},
        )
        try:
            result = await service.run(
                message=turn.input_message,
                conversation_summary=self._conversation_summary(turn),
            )
            turn._capture_public_navigation_references(service.working_items)
        except Exception:
            context.emit(
                "reasoning.failed",
                "Corrección no completada",
                {"activity_id": activity_id},
            )
            raise
        _ensure_turn_control_current(turn)
        context.emit(
            "reasoning.completed",
            "Ejecución corregida",
            {"activity_id": activity_id, "confidence": result.confidence},
        )
        if not result.plan:
            return self._read_only_response(turn, result, policy)

        try:
            prepared = await plans.prepare(result.plan)
        except CapabilityPlanStepError as prepare_error:
            return await self._repair_recoverable_plan(
                turn,
                lease_token=lease_token,
                envelope=envelope,
                error=prepare_error,
                plans=plans,
                policy=policy,
                registry=registry,
                context=context,
                executor=executor,
                working_items=service.working_items,
            )
        prepared_items = _append_plan_prepared(service.working_items, prepared)
        repaired_envelope = {
            "format_version": 1,
            "answer": result.answer,
            "confidence": result.confidence,
            "human_approved": False,
            "plan": prepared,
        }
        if plans.approval_refines(source_plan, prepared):
            authorized = dict(prepared)
            authorized["state"] = "authorized"
            repaired_envelope["human_approved"] = bool(envelope.get("human_approved"))
            repaired_envelope["plan"] = authorized
            return await self._execute_plan(
                turn,
                lease_token=lease_token,
                envelope=repaired_envelope,
                plans=plans,
                policy=policy,
                registry=registry,
                context=context,
                executor=executor,
                working_items=prepared_items,
            )
        if prepared["requires_confirmation"]:
            turn.with_user(SUPERUSER_ID).write(
                {"working_items_payload": transcript_payload(prepared_items)}
            )
            response = self._plan_response(turn, repaired_envelope, policy)
            self._persist_awaiting_plan(turn, repaired_envelope, response)
            return response
        return await self._execute_plan(
            turn,
            lease_token=lease_token,
            envelope=repaired_envelope,
            plans=plans,
            policy=policy,
            registry=registry,
            context=context,
            executor=executor,
            working_items=prepared_items,
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
