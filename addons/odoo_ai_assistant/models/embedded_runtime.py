"""Definitive Odoo-owned composition root for embedded Assistant turns."""

from __future__ import annotations

import asyncio
import re

from odoo import api, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime import RuntimePaths, detect_codex
from ..runtime.agent import AgentTurnService
from ..runtime.agent.codex import CodexAgentSettings, CodexReasoningEngine
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)
from .chat_policy import resolve_capability_policy

_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,128}$")


class EmbeddedAssistantRuntime(models.AbstractModel):
    _name = "odoo.ai.embedded.runtime"
    _description = "Odoo AI Assistant Embedded Runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        """Compose and run one persisted turn under the originating user Environment."""

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
            from .turn_queue import _append_event

            _append_event(
                dbname,
                turn.id,
                event_type,
                title,
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
        settings = self._codex_settings(turn)

        def cancellation_requested():
            from .turn_queue import _cancellation_requested

            return _cancellation_requested(dbname, turn.id, lease_token)

        reasoning = CodexReasoningEngine(
            settings,
            cancellation_requested=cancellation_requested,
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            reasoning_engine=reasoning,
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
        if result.plan:
            # Plan capabilities are already registry-validated, but write persistence and
            # execution must be bound to the existing approval/receipt state machine before
            # the queue may treat them as completed.
            raise EmbeddedRuntimeError("agent_plan_runtime_not_migrated")
        event_sink(
            "reasoning.completed",
            "Respuesta preparada",
            {"confidence": result.confidence},
        )
        return self._read_only_response(turn, result, policy_snapshot)

    def _codex_settings(self, turn):
        parameters = self.env["ir.config_parameter"]
        configured = parameters._get_param("odoo_ai_assistant.codex_executable") or None
        status = detect_codex(configured)
        if not status.ready or status.executable is None:
            raise EmbeddedRuntimeError("codex_runtime_not_found")
        paths = RuntimePaths.from_odoo().ensure()
        return CodexAgentSettings(
            executable=status.executable,
            codex_home=paths.codex_home,
            model=turn.reasoning_model or None,
        )

    def _conversation_summary(self, turn):
        if not turn.conversation_id:
            return ""
        domain = [
            ("conversation_id", "=", turn.conversation_id.id),
            ("user_id", "=", self.env.uid),
        ]
        if turn.user_message_id:
            domain.append(("id", "!=", turn.user_message_id.id))
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

    def _read_only_response(self, turn, result, policy):
        conversation_id = (
            turn.conversation_id.conversation_uuid if turn.conversation_id else None
        )
        goal = " ".join((turn.input_message or "").split())[:1_000]
        return {
            "ok": True,
            "turn_id": turn.turn_uuid,
            "conversation_id": conversation_id,
            "workflow": "AGENT",
            "answer": result.answer,
            "confidence": result.confidence,
            "limitations": [],
            "citations": [],
            "plan": {
                "plan_id": turn.turn_uuid,
                "state": "completed",
                "risk": "low",
                "metadata": {
                    "needs_read": True,
                    "needs_schema": True,
                    "needs_write": False,
                    "needs_business_action": False,
                    "has_external_effect": False,
                    "has_irreversible_effect": False,
                    "is_atomic": True,
                    "estimated_blast_radius": 0,
                },
                "policy": {
                    "confirmation_mode": policy["confirmation_mode"],
                    "max_auto_risk": policy["max_auto_risk"],
                    "allow_synthetic_data": policy["allow_synthetic_data"],
                    "constrained_by": [],
                },
                "goal": goal or "Responder a la petición del usuario.",
                "assumptions": [],
                "steps": [],
                "requires_confirmation": False,
                "expires_at": None,
            },
        }


class AssistantTurnEmbeddedStatus(models.Model):
    _inherit = "odoo.ai.turn"

    def browser_status(self, *, after_sequence=0):
        payload = super().browser_status(after_sequence=after_sequence)
        self.ensure_one()
        response = self.result_payload if self.state == "completed" else None
        payload["response"] = dict(response) if isinstance(response, dict) else None
        return payload


class EmbeddedRuntimeError(RuntimeError):
    def __init__(self, code):
        normalized = (
            code
            if isinstance(code, str) and _ERROR_CODE.fullmatch(code)
            else "runtime_unavailable"
        )
        super().__init__(normalized)
        self.code = normalized
