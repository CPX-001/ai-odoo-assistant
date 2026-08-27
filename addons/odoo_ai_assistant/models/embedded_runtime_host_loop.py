"""Current ADR-019 host-loop composition for persisted embedded Assistant turns."""

from __future__ import annotations

import asyncio

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime.agent import AgentTurnService, CapabilityPlanError, CapabilityPlanService
from ..runtime.agent.codex_decision import CodexDecisionEngine
from ..runtime.agent.working_transcript import (
    WorkingTranscriptError,
    append_working_item,
    transcript_payload,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)
from .chat_policy import resolve_capability_policy
from .embedded_runtime import EmbeddedRuntimeError, _commit_plan_barrier, _plan_envelope
from .turn_working_transcript import persist_working_transcript


class EmbeddedAssistantHostLoopRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        """Run ADR-019 under the originating effective Odoo user."""

        if self.env.su:
            raise AccessError("Assistant embedded runtime cannot run in superuser mode")
        if type(turn_id) is not int or turn_id <= 0 or not isinstance(lease_token, str):
            raise ValidationError("Invalid Assistant turn binding")
        turn = self.env["odoo.ai.turn"].browse(turn_id).exists()
        if (
            not turn
            or turn.user_id.id != self.env.uid
            or turn.company_id.id != self.env.company.id
            or turn.state != "running"
            or turn.lease_token != lease_token
        ):
            raise AccessError("Assistant turn binding is no longer valid")

        policy_snapshot = resolve_capability_policy(turn.policy_payload or {})
        registry = discover_capabilities()
        resolver = CapabilityConfigResolver.from_env(self.env)
        enablement = resolver.enablement_overrides(registry.definitions)
        dbname = self.env.cr.dbname

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
            conversation_id=(
                turn.conversation_id.conversation_uuid if turn.conversation_id else None
            ),
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
        plans = CapabilityPlanService(registry=registry, executor=executor)

        envelope = _plan_envelope(turn.capability_plan_payload)
        if envelope is not None and envelope["plan"]["state"] == "authorized":
            return asyncio.run(
                self._execute_plan(
                    turn,
                    lease_token=lease_token,
                    envelope=envelope,
                    plans=plans,
                    policy=policy_snapshot,
                )
            )

        settings = self._codex_settings(turn)

        def cancellation_requested():
            from .turn_queue import _cancellation_requested

            return _cancellation_requested(dbname, turn.id, lease_token)

        try:
            working_items = turn._working_items_from_turn(turn)
        except WorkingTranscriptError as error:
            raise EmbeddedRuntimeError(error.code) from error

        def persist(items):
            try:
                persist_working_transcript(
                    dbname,
                    turn.id,
                    lease_token,
                    items,
                )
            except RuntimeError as error:
                raise EmbeddedRuntimeError(str(error)) from error

        decision_engine = CodexDecisionEngine(
            settings,
            cancellation_requested=cancellation_requested,
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=decision_engine,
            working_items=working_items,
            persist_working_items=persist,
            cancellation_requested=cancellation_requested,
            allow_plan_proposals=True,
        )
        event_sink(
            "reasoning.started",
            "Analizando petición",
            {"reasoning_capabilities": len(registry.for_reasoning(context))},
        )
        result = asyncio.run(
            service.run(
                message=turn.input_message,
                conversation_summary=self._conversation_summary(turn),
            )
        )
        event_sink(
            "reasoning.completed",
            "Respuesta preparada",
            {"confidence": result.confidence},
        )
        if not result.plan:
            return self._read_only_response(turn, result, policy_snapshot)

        if len(result.plan) != 1:
            raise EmbeddedRuntimeError("agent_plan_limit_exceeded")
        prepared = asyncio.run(plans.prepare(result.plan))
        prepared_items = _append_plan_prepared(service.working_items, prepared)
        envelope = {
            "format_version": 1,
            "answer": result.answer,
            "confidence": result.confidence,
            "human_approved": False,
            "plan": prepared,
        }
        if prepared["requires_confirmation"]:
            # Persist plan and its private boundary in the same current Odoo transaction.
            turn.with_user(SUPERUSER_ID).write(
                {"working_items_payload": transcript_payload(prepared_items)}
            )
            response = self._plan_response(turn, envelope, policy_snapshot)
            self._persist_awaiting_plan(turn, envelope, response)
            return response
        return asyncio.run(
            self._execute_plan(
                turn,
                lease_token=lease_token,
                envelope=envelope,
                plans=plans,
                policy=policy_snapshot,
                working_items=prepared_items,
            )
        )

    async def _execute_plan(
        self,
        turn,
        *,
        lease_token,
        envelope,
        plans,
        policy,
        working_items=None,
    ):
        """Execute the unchanged action lifecycle and persist a verified private receipt."""

        dbname = self.env.cr.dbname
        if working_items is None:
            try:
                working_items = turn._working_items_from_turn(turn)
            except WorkingTranscriptError as error:
                raise EmbeddedRuntimeError(error.code) from error

        def before_effect():
            # Existing separately committed barrier remains the no-blind-retry authority.
            _commit_plan_barrier(
                dbname,
                turn.id,
                lease_token,
                envelope,
            )
            # The plan boundary is durable before the first effect. If this second commit
            # is interrupted the already-durable barrier still forces recovery.
            persist_working_transcript(
                dbname,
                turn.id,
                lease_token,
                working_items,
            )

        try:
            executed = await plans.execute(
                envelope["plan"],
                human_approved=bool(envelope["human_approved"]),
                before_effect=before_effect,
            )
        except (CapabilityPlanError, CapabilityError) as error:
            raise EmbeddedRuntimeError(error.code) from error

        completed = dict(envelope)
        completed["plan"] = executed.payload
        receipt_items = append_working_item(
            working_items,
            "verified_effect_receipt",
            {
                "verified": True,
                "plan_state": executed.payload["state"],
                "step_count": len(executed.payload["steps"]),
                "capabilities": [
                    step["capability"] for step in executed.payload["steps"]
                ],
            },
        )
        # Business effects, verification, plan result and receipt share this cursor.
        # The caller commits them together; failure after the durable barrier is recovery-only.
        turn.with_user(SUPERUSER_ID).write(
            {
                "capability_plan_payload": completed,
                "working_items_payload": transcript_payload(receipt_items),
            }
        )
        return self._plan_response(turn, completed, policy, completed=True)


def _append_plan_prepared(working_items, prepared):
    steps = prepared.get("steps") if isinstance(prepared, dict) else None
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    proposed = next(
        (item for item in reversed(working_items) if item.kind == "plan_step_proposed"),
        None,
    )
    if proposed is None:
        raise EmbeddedRuntimeError("agent_working_transcript_invalid")
    call_id = proposed.data.get("call_id")
    capability = proposed.data.get("capability")
    if not isinstance(call_id, str) or not isinstance(capability, str):
        raise EmbeddedRuntimeError("agent_working_transcript_invalid")
    if steps[0].get("capability") != capability:
        raise EmbeddedRuntimeError("capability_plan_binding_mismatch")
    return append_working_item(
        working_items,
        "plan_prepared",
        {
            "call_id": call_id,
            "capability": capability,
            "state": prepared.get("state"),
            "requires_confirmation": prepared.get("requires_confirmation") is True,
            "step_count": 1,
        },
    )
