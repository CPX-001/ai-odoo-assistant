"""Current host-loop composition for persisted embedded Assistant turns.

This overlay keeps the legacy monolithic implementation in ``embedded_runtime.py`` as a
rollback seam while making the ADR-019 one-decision host loop the active product path.
"""

from __future__ import annotations

import asyncio

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime.agent import AgentTurnService, CapabilityPlanService
from ..runtime.agent.codex_decision import CodexDecisionEngine
from ..runtime.agent.working_transcript import WorkingTranscriptError
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)
from .chat_policy import resolve_capability_policy
from .embedded_runtime import EmbeddedRuntimeError, _plan_envelope
from .turn_working_transcript import persist_working_transcript


class EmbeddedAssistantHostLoopRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        """Run the current ADR-019 host loop under the originating user Environment."""

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
                code = str(error)
                raise EmbeddedRuntimeError(code) from error

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
            allow_plan_proposals=False,
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
        if result.plan:
            # E2E-3 intentionally keeps PLAN disabled until the next validated slice.
            raise EmbeddedRuntimeError("agent_plan_proposal_not_enabled")
        return self._read_only_response(turn, result, policy_snapshot)
