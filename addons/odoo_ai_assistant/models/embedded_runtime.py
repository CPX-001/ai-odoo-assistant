"""Definitive Odoo-owned composition root for embedded Assistant turns."""

from __future__ import annotations

import asyncio
import re

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime import RuntimePaths, detect_codex
from ..runtime.agent import AgentTurnService, CapabilityPlanError, CapabilityPlanService
from ..runtime.agent.codex import CodexAgentSettings, CodexReasoningEngine
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)
from .chat_policy import resolve_capability_policy

_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,128}$")
_PLAN_ENVELOPE_KEYS = {
    "format_version",
    "answer",
    "confidence",
    "human_approved",
    "plan",
}


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
        event_sink(
            "reasoning.completed",
            "Respuesta preparada",
            {"confidence": result.confidence},
        )
        if not result.plan:
            return self._read_only_response(turn, result, policy_snapshot)

        prepared = asyncio.run(plans.prepare(result.plan))
        envelope = {
            "format_version": 1,
            "answer": result.answer,
            "confidence": result.confidence,
            "human_approved": False,
            "plan": prepared,
        }
        if prepared["requires_confirmation"]:
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
            )
        )

    async def _execute_plan(self, turn, *, lease_token, envelope, plans, policy):
        def before_effect():
            _commit_plan_barrier(
                turn,
                lease_token,
                envelope,
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
        turn.with_user(SUPERUSER_ID).write({"capability_plan_payload": completed})
        return self._plan_response(turn, completed, policy, completed=True)

    def _persist_awaiting_plan(self, turn, envelope, response):
        technical = turn.with_user(SUPERUSER_ID)
        assistant_message = self.env["odoo.ai.message"].with_user(SUPERUSER_ID).create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "assistant",
                "content": response["answer"],
                "internal_workflow": "AGENT",
            }
        )
        technical.write(
            {
                "state": "awaiting_confirmation",
                "capability_plan_payload": envelope,
                "result_payload": response,
                "assistant_message_id": assistant_message.id,
                "lease_token": False,
                "lease_expires_at": False,
                "heartbeat_at": fields.Datetime.now(),
            }
        )
        if turn.conversation_id:
            turn.conversation_id.with_user(SUPERUSER_ID).write(
                {"last_message_at": fields.Datetime.now()}
            )
        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=technical,
            event_type="approval.required",
            title="Esperando confirmación",
            payload={"plan_id": turn.turn_uuid},
        )

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
        return _browser_response(
            turn,
            answer=result.answer,
            confidence=result.confidence,
            plan=_browser_empty_plan(turn, policy),
        )

    def _plan_response(self, turn, envelope, policy, *, completed=False):
        plan = _browser_capability_plan(turn, envelope["plan"], policy)
        answer = envelope["answer"]
        confidence = envelope["confidence"]
        if completed:
            answer = _completion_answer(envelope["plan"])
            confidence = "high"
        return _browser_response(
            turn,
            answer=answer,
            confidence=confidence,
            plan=plan,
        )


class AssistantTurnEmbeddedStatus(models.Model):
    _inherit = "odoo.ai.turn"

    capability_plan_payload = fields.Json(readonly=True)

    @api.model
    def decide_capability_plan_for_current_user(self, plan_id, decision):
        if decision not in {"approve", "reject"}:
            raise ValidationError("Invalid Assistant plan decision")
        turn = self._owned_turn(plan_id)
        if turn.state != "awaiting_confirmation":
            raise ValidationError("Assistant plan is not awaiting confirmation")
        envelope = _plan_envelope(turn.capability_plan_payload)
        if envelope is None or envelope["plan"]["state"] != "awaiting_confirmation":
            raise ValidationError("Assistant plan is unavailable")
        technical = turn.with_user(SUPERUSER_ID)
        if decision == "reject":
            plan = dict(envelope["plan"])
            plan["state"] = "rejected"
            envelope = dict(envelope)
            envelope["plan"] = plan
            response = dict(turn.result_payload or {})
            response["answer"] = "Acción cancelada. No se ha realizado ningún cambio."
            response["confidence"] = "high"
            if isinstance(response.get("plan"), dict):
                response["plan"] = {**response["plan"], "state": "rejected"}
            assistant_message = self.env["odoo.ai.message"].with_user(SUPERUSER_ID).create(
                {
                    "conversation_id": turn.conversation_id.id,
                    "role": "assistant",
                    "content": response["answer"],
                    "internal_workflow": "AGENT",
                }
            )
            technical.write(
                {
                    "state": "completed",
                    "capability_plan_payload": envelope,
                    "result_payload": response,
                    "assistant_message_id": assistant_message.id,
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=technical,
                event_type="approval.rejected",
                title="Acción rechazada",
            )
            return {
                "ok": True,
                "plan_id": turn.turn_uuid,
                "state": "rejected",
                "plan": response.get("plan"),
                "response": response,
            }

        plan = dict(envelope["plan"])
        plan["state"] = "authorized"
        envelope = dict(envelope)
        envelope["plan"] = plan
        envelope["human_approved"] = True
        technical.write(
            {
                "state": "queued",
                "queued_at": fields.Datetime.now(),
                "capability_plan_payload": envelope,
                "result_payload": False,
                "error_code": False,
                "lease_token": False,
                "lease_expires_at": False,
            }
        )
        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=technical,
            event_type="approval.approved",
            title="Acción aprobada",
        )
        self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_1")._trigger()
        self.env.ref("odoo_ai_assistant.ir_cron_assistant_turn_slot_2")._trigger()
        policy = resolve_capability_policy(turn.policy_payload or {})
        return {
            "ok": True,
            "plan_id": turn.turn_uuid,
            "state": "authorized",
            "plan": _browser_capability_plan(turn, plan, policy),
            "response": None,
        }

    @api.model
    def capability_plan_status_for_current_user(self, plan_id):
        turn = self._owned_turn(plan_id)
        response = turn.result_payload if isinstance(turn.result_payload, dict) else None
        plan = response.get("plan") if isinstance(response, dict) and isinstance(response.get("plan"), dict) else None
        envelope = _plan_envelope(turn.capability_plan_payload)
        if plan is None and envelope is not None:
            policy = resolve_capability_policy(turn.policy_payload or {})
            plan = _browser_capability_plan(turn, envelope["plan"], policy)
        state = plan.get("state") if isinstance(plan, dict) else turn.state
        return {
            "ok": True,
            "plan_id": turn.turn_uuid,
            "state": state,
            "plan": plan,
            "turn_state": turn.state,
            "response": response,
            "error_code": turn.error_code or None,
        }


class EmbeddedRuntimeError(RuntimeError):
    def __init__(self, code):
        normalized = (
            code
            if isinstance(code, str) and _ERROR_CODE.fullmatch(code)
            else "runtime_unavailable"
        )
        super().__init__(normalized)
        self.code = normalized


def _commit_plan_barrier(turn, lease_token, envelope, *, working_items_payload=None):
    """Commit pending pre-effect activity and the durable barrier on the worker cursor."""

    technical = turn.with_user(SUPERUSER_ID).exists()
    technical.invalidate_recordset(["state", "lease_token"])
    if (
        not technical
        or technical.state != "running"
        or technical.lease_token != lease_token
    ):
        raise EmbeddedRuntimeError("agent_turn_lease_lost")
    values = {
        "capability_plan_payload": envelope,
        "write_barrier": True,
        "heartbeat_at": fields.Datetime.now(),
    }
    if working_items_payload is not None:
        values["working_items_payload"] = working_items_payload
    technical.write(values)
    technical.env["odoo.ai.turn.event"].append_for_turn(
        turn=technical,
        event_type="execution.barrier",
        title="Ejecutando acción autorizada",
    )
    technical.env.cr.commit()


def _plan_envelope(value):
    if not value:
        return None
    if not isinstance(value, dict) or set(value) != _PLAN_ENVELOPE_KEYS:
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    if (
        value.get("format_version") != 1
        or not isinstance(value.get("answer"), str)
        or value.get("confidence") not in {"high", "medium", "low"}
        or type(value.get("human_approved")) is not bool
        or not isinstance(value.get("plan"), dict)
    ):
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    return dict(value)


def _browser_response(turn, *, answer, confidence, plan):
    return {
        "ok": True,
        "turn_id": turn.turn_uuid,
        "conversation_id": (
            turn.conversation_id.conversation_uuid if turn.conversation_id else None
        ),
        "workflow": "AGENT",
        "answer": answer,
        "confidence": confidence,
        "limitations": [],
        "citations": [],
        "plan": plan,
    }


def _browser_empty_plan(turn, policy):
    return {
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
        "policy": _browser_policy(policy),
        "goal": _goal(turn),
        "assumptions": [],
        "steps": [],
        "requires_confirmation": False,
        "expires_at": None,
    }


def _browser_capability_plan(turn, plan, policy):
    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    risk = "low"
    browser_steps = []
    for step in steps:
        if not isinstance(step, dict):
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        risk = _max_risk(risk, step.get("risk"))
        preview = step.get("preview")
        if not isinstance(preview, dict):
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        receipt = None
        result = step.get("result")
        if isinstance(result, dict):
            receipt = {
                "error_code": None,
                "evidence_id": None,
                "outcome": "verified" if step.get("verification") is not None else "completed",
                "record_id": result.get("record_id"),
                "record_model": result.get("model"),
            }
        browser_steps.append(
            {
                "step_id": f"{turn.turn_uuid}:{step.get('position')}",
                "capability": step.get("capability"),
                "title": step.get("title") or step.get("capability"),
                "summary": _preview_summary(preview),
                "state": step.get("state"),
                "risk": step.get("risk"),
                "effect_scope": step.get("effect"),
                "approval": step.get("approval"),
                "preview": preview,
                "receipt": receipt,
            }
        )
    return {
        "plan_id": turn.turn_uuid,
        "state": plan.get("state"),
        "risk": risk,
        "metadata": {
            "needs_read": False,
            "needs_schema": False,
            "needs_write": True,
            "needs_business_action": any(
                step.get("risk") in {"high", "protected"} for step in steps
            ),
            "has_external_effect": any(step.get("effect") == "external" for step in steps),
            "has_irreversible_effect": any(
                step.get("effect") == "internal_irreversible" for step in steps
            ),
            "is_atomic": True,
            "estimated_blast_radius": len(steps),
        },
        "policy": _browser_policy(policy),
        "goal": _goal(turn),
        "assumptions": [],
        "steps": browser_steps,
        "requires_confirmation": bool(plan.get("requires_confirmation")),
        "expires_at": None,
    }


def _preview_summary(preview):
    operation = preview.get("operation")
    display_name = preview.get("display_name")
    model = preview.get("model")
    record_id = preview.get("record_id")
    parts = []
    if isinstance(operation, str) and operation:
        parts.append(operation.replace("_", " "))
    if isinstance(display_name, str) and display_name.strip():
        parts.append(display_name.strip())
    elif isinstance(model, str) and model:
        target = model
        if type(record_id) is int and record_id > 0:
            target = f"{target} #{record_id}"
        parts.append(target)
    changes = preview.get("changes")
    if isinstance(changes, list) and changes:
        parts.append(f"{len(changes)} cambio(s)")
    return " · ".join(parts)[:500] or "Revisa el preview antes de continuar."


def _browser_policy(policy):
    return {
        "confirmation_mode": policy["confirmation_mode"],
        "max_auto_risk": policy["max_auto_risk"],
        "allow_synthetic_data": policy["allow_synthetic_data"],
        "constrained_by": [],
    }


def _goal(turn):
    normalized = " ".join((turn.input_message or "").split())[:1_000]
    return normalized or "Completar la petición del usuario."


def _completion_answer(plan):
    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    if len(steps) == 1:
        title = steps[0].get("title") if isinstance(steps[0], dict) else None
        if isinstance(title, str) and title.strip():
            return f"He completado y verificado la acción: {title.strip()}"
    return "He completado y verificado las acciones solicitadas."


def _max_risk(left, right):
    order = {"low": 0, "moderate": 1, "high": 2, "protected": 3}
    if right not in order:
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    return right if order[right] > order[left] else left
