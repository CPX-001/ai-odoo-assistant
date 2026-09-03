"""Current ADR-019 host-loop composition for persisted embedded Assistant turns."""

from __future__ import annotations

import asyncio
import secrets

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError, ValidationError

from ..runtime.agent import (
    AgentTurnResult,
    AgentTurnService,
    AssistantExtensionDecisionEngine,
    CapabilityPlanError,
    CapabilityPlanService,
    CapabilityPlanStepError,
    PostEffectDecisionEngine,
    current_codex_provider_profile,
)
from ..runtime.agent.business_outcome import (
    incomplete_effect_answer,
    incomplete_effect_summary,
)
from ..runtime.agent.interactive_codex import InteractiveCodexDecisionEngine
from ..runtime.agent.planning import PlanningDecisionEngine
from ..runtime.agent.provider_failure import (
    FailureNormalizingDecisionEngine,
    ProviderFailureError,
)
from ..runtime.agent.social import simple_social_answer
from ..runtime.agent.telemetry import emit_optional_telemetry
from ..runtime.agent.turn_effect_boundary import acquire_turn_effect_lock
from ..runtime.agent.working_transcript import (
    MAX_TRANSCRIPT_BYTES,
    WorkingItem,
    WorkingTranscriptError,
    append_working_item,
    transcript_payload,
    working_transcript_bytes,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_assistant_extensions_for_env,
    discover_capabilities_for_env,
    technical_access_profile_for_env,
)
from .chat_policy import resolve_capability_policy
from .embedded_runtime import EmbeddedRuntimeError, _commit_plan_barrier, _plan_envelope
from .turn_working_transcript import persist_working_transcript

_COMPACT_RECEIPT_SCALARS = (
    "operation",
    "model",
    "outcome",
    "reason",
    "executed",
    "verified",
    "count",
    "requested_count",
    "failed_count",
    "excluded_count",
    "omitted_retained_count",
)
_COMPACT_RECEIPT_ID_SAMPLE = 20
_COMPACT_RECEIPT_GROUP_SAMPLE = 5
_COMPACT_RECEIPT_GROUP_ID_SAMPLE = 10
_POST_EFFECT_CONTINUATION_HEADROOM_BYTES = 64 * 1024


class EmbeddedAssistantHostLoopRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        """Run the provider-neutral host loop under the originating effective Odoo user."""

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
        social_answer = simple_social_answer(turn.input_message, lang=turn.lang)
        if social_answer is not None:
            _ensure_turn_control_current(turn)
            return self._read_only_response(
                turn,
                AgentTurnResult(
                    answer=social_answer,
                    confidence="high",
                    plan=(),
                ),
                policy_snapshot,
            )
        registry = discover_capabilities_for_env(self.env)
        resolver = CapabilityConfigResolver.from_env(self.env)
        enablement = resolver.enablement_overrides(registry.definitions)
        settings_snapshot = turn.execution_settings_snapshot() or {}
        planning_strategy = settings_snapshot.get("planning_strategy")
        dbname = self.env.cr.dbname

        def event_sink(event_type, title, payload):
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn.with_user(SUPERUSER_ID),
                event_type=event_type,
                title=title,
                payload=dict(payload),
            )

        metadata = {
            "capability_enabled": enablement,
            "capability_policy": policy_snapshot,
        }
        if isinstance(planning_strategy, dict):
            metadata["planning_strategy"] = dict(planning_strategy)
        context = CapabilityContext(
            env=self.env,
            turn_id=turn.turn_uuid,
            conversation_id=(
                turn.conversation_id.conversation_uuid if turn.conversation_id else None
            ),
            screen=turn.screen_payload or {},
            event_sink=event_sink,
            metadata=metadata,
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
                    registry=registry,
                    context=context,
                    executor=executor,
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

        control_snapshot = turn.runtime_control_snapshot(turn.turn_uuid)
        if control_snapshot["cancel_requested"]:
            raise EmbeddedRuntimeError("agent_cancelled")
        if control_snapshot["sequence"] > control_snapshot["applied_sequence"]:
            working_items = ()
            try:
                persist_working_transcript(turn, lease_token, working_items)
            except RuntimeError as error:
                raise EmbeddedRuntimeError(str(error)) from error

        def persist(items):
            try:
                persist_working_transcript(turn, lease_token, items)
            except RuntimeError as error:
                raise EmbeddedRuntimeError(str(error)) from error

        extension_engine = _with_assistant_extensions(
            self.env,
            FailureNormalizingDecisionEngine(
                InteractiveCodexDecisionEngine(
                    settings,
                    cancellation_requested=cancellation_requested,
                ),
                component="codex",
                effect_state="none",
            ),
            registry=registry,
            config=resolver,
        )
        decision_engine = PlanningDecisionEngine(extension_engine)
        reasoning_activity_id = None

        def on_work_started():
            nonlocal reasoning_activity_id
            if reasoning_activity_id is not None:
                return
            reasoning_activity_id = _new_reasoning_activity_id()
            emit_optional_telemetry(
                context,
                "reasoning.started",
                "Procesando solicitud",
                {
                    "reasoning_capabilities": len(registry.for_reasoning(context)),
                    "activity_id": reasoning_activity_id,
                },
            )

        def build_service(items):
            return AgentTurnService(
                registry=registry,
                context=context,
                executor=executor,
                decision_engine=decision_engine,
                working_items=items,
                persist_working_items=persist,
                cancellation_requested=cancellation_requested,
                allow_plan_proposals=True,
                on_work_started=on_work_started,
            )

        service = build_service(working_items)
        try:
            result = asyncio.run(
                service.run(
                    message=turn.input_message,
                    conversation_summary=self._conversation_summary(turn),
                )
            )
            _ensure_turn_control_current(turn)
            turn._capture_public_navigation_references(service.working_items)
        except Exception:
            if reasoning_activity_id is not None:
                emit_optional_telemetry(
                    context,
                    "reasoning.failed",
                    "Procesamiento no completado",
                    {"activity_id": reasoning_activity_id},
                )
            raise
        prepared = None
        while result.plan:
            try:
                prepared = asyncio.run(plans.prepare(result.plan))
                break
            except CapabilityPlanStepError as error:
                repaired_items = _append_prepare_error(
                    service.working_items,
                    error,
                )
                persist(repaired_items)
                replan_count = sum(
                    item.kind == "plan_execution_error" for item in repaired_items
                )
                max_replans = policy_snapshot.get("max_replans", 0)
                service = build_service(repaired_items)
                if type(max_replans) is not int or replan_count > max_replans:
                    result = asyncio.run(service.finish_safely(error.code))
                    prepared = None
                    break
                result = asyncio.run(
                    service.run(
                        message=turn.input_message,
                        conversation_summary=self._conversation_summary(turn),
                    )
                )
                _ensure_turn_control_current(turn)
                turn._capture_public_navigation_references(service.working_items)

        if reasoning_activity_id is not None:
            emit_optional_telemetry(
                context,
                "reasoning.completed",
                "Respuesta preparada",
                {"confidence": result.confidence, "activity_id": reasoning_activity_id},
            )
        if not result.plan:
            response = self._read_only_response(turn, result, policy_snapshot)
            response["citations"] = extension_engine.browser_citations()
            return response

        if prepared is None:
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        _ensure_turn_control_current(turn)
        prepared_items = _append_plan_prepared(service.working_items, prepared)
        envelope = {
            "format_version": 1,
            "answer": result.answer,
            "confidence": result.confidence,
            "human_approved": False,
            "plan": prepared,
        }
        if prepared["requires_confirmation"]:
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
                registry=registry,
                context=context,
                executor=executor,
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
        registry,
        context,
        executor,
        working_items=None,
    ):
        """Execute, verify, append an authoritative receipt and synthesize the final answer."""

        if working_items is None:
            try:
                working_items = turn._working_items_from_turn(turn)
            except WorkingTranscriptError as error:
                raise EmbeddedRuntimeError(error.code) from error

        def before_effect():
            acquire_turn_effect_lock(turn.env.cr, turn.turn_uuid)
            _ensure_turn_control_current(turn)
            _commit_plan_barrier(
                turn,
                lease_token,
                envelope,
                working_items_payload=transcript_payload(working_items),
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
        receipt_items = _append_verified_effect_receipt(working_items, executed.payload)
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

    async def _continue_after_effect(
        self,
        turn,
        *,
        lease_token,
        completed,
        policy,
        registry,
        context,
        executor,
        working_items,
    ):
        """Reason from the verified receipt without exposing another PLAN authority surface."""

        incomplete = incomplete_effect_summary(completed["plan"].get("steps", []))
        if incomplete is not None:
            natural = dict(completed)
            natural["answer"] = incomplete_effect_answer(
                incomplete,
                spanish=(
                    not isinstance(turn.lang, str)
                    or turn.lang.lower().startswith("es")
                ),
            )
            natural["confidence"] = "high"
            grounded_items = append_working_item(
                working_items,
                "final_answer",
                {
                    "answer": natural["answer"],
                    "confidence": "high",
                    "host_grounded_outcome": True,
                },
            )
            try:
                persist_working_transcript(turn, lease_token, grounded_items)
            except RuntimeError as error:
                raise EmbeddedRuntimeError(str(error)) from error
            return self._plan_response(turn, natural, policy)

        dbname = self.env.cr.dbname

        def cancellation_requested():
            from .turn_queue import _cancellation_requested

            return _cancellation_requested(dbname, turn.id, lease_token)

        def persist(items):
            try:
                persist_working_transcript(turn, lease_token, items)
            except RuntimeError as error:
                raise EmbeddedRuntimeError(str(error)) from error

        resolver = CapabilityConfigResolver.from_env(self.env)
        decision_engine = PlanningDecisionEngine(
            _with_assistant_extensions(
                self.env,
                PostEffectDecisionEngine(
                    FailureNormalizingDecisionEngine(
                        InteractiveCodexDecisionEngine(
                            self._codex_settings(turn),
                            cancellation_requested=cancellation_requested,
                        ),
                        component="codex",
                        effect_state="confirmed",
                    )
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
            working_items=working_items,
            persist_working_items=persist,
            cancellation_requested=cancellation_requested,
            allow_plan_proposals=False,
        )
        reasoning_activity_id = _new_reasoning_activity_id()
        emit_optional_telemetry(
            context,
            "reasoning.started",
            "Sintetizando resultado verificado",
            {"post_effect": True, "activity_id": reasoning_activity_id},
        )
        synthesis_failed = False
        try:
            result = await service.run(
                message=turn.input_message,
                conversation_summary=self._conversation_summary(turn),
            )
            _ensure_turn_control_current(turn)
            turn._capture_public_navigation_references(service.working_items)
        except ProviderFailureError as error:
            synthesis_failed = True
            emit_optional_telemetry(
                context,
                "reasoning.failed",
                "Síntesis no completada",
                {"post_effect": True, "activity_id": reasoning_activity_id},
            )
            result = await service.finish_safely(error.code)
        except Exception:
            emit_optional_telemetry(
                context,
                "reasoning.failed",
                "Síntesis no completada",
                {"post_effect": True, "activity_id": reasoning_activity_id},
            )
            raise
        if result.plan:
            raise EmbeddedRuntimeError("agent_post_effect_plan_forbidden")
        if not synthesis_failed:
            emit_optional_telemetry(
                context,
                "reasoning.completed",
                "Respuesta final preparada",
                {
                    "confidence": result.confidence,
                    "post_effect": True,
                    "activity_id": reasoning_activity_id,
                },
            )
        natural = dict(completed)
        natural["answer"], natural["confidence"] = _grounded_post_effect_result(
            completed["plan"],
            provider_answer=result.answer,
            provider_confidence=result.confidence,
            lang=turn.lang,
        )
        return self._plan_response(turn, natural, policy)


def _with_assistant_extensions(env, provider, *, registry, config):
    """Compose the Phase-7 non-authoritative extension layer around any decision provider."""

    return AssistantExtensionDecisionEngine(
        provider,
        registry=registry,
        extensions=discover_assistant_extensions_for_env(
            env,
            capability_registry=registry,
        ),
        provider_profile=current_codex_provider_profile(),
        config=config,
        technical_profile=technical_access_profile_for_env(env),
    )


def _ensure_turn_control_current(turn):
    snapshot = turn.runtime_control_snapshot(turn.turn_uuid)
    if snapshot["cancel_requested"]:
        raise EmbeddedRuntimeError("agent_cancelled")
    if snapshot["sequence"] != snapshot["applied_sequence"]:
        raise EmbeddedRuntimeError("agent_redirected")


def _new_reasoning_activity_id():
    return f"activity:v1:{secrets.token_hex(16)}"


def _grounded_post_effect_result(
    plan,
    *,
    provider_answer,
    provider_confidence,
    lang,
):
    """Keep a provider summary only when it cannot contradict an incomplete receipt."""

    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    incomplete = incomplete_effect_summary(steps)
    if incomplete is None:
        return provider_answer, provider_confidence
    spanish = not isinstance(lang, str) or lang.lower().startswith("es")
    return incomplete_effect_answer(incomplete, spanish=spanish), "high"


def _append_prepare_error(working_items, error):
    payload = {
        "code": error.code,
        "step_id": error.step_id,
        "capability": error.capability,
        "phase": "prepare",
        "details": dict(error.details),
        "effect_state": "none",
        "rolled_back": False,
        "replan": 1 + sum(
            item.kind == "plan_execution_error" for item in working_items
        ),
    }
    try:
        return append_working_item(working_items, "plan_execution_error", payload)
    except WorkingTranscriptError as transcript_error:
        if not payload["details"] or transcript_error.code != "agent_working_item_too_large":
            raise EmbeddedRuntimeError(transcript_error.code) from transcript_error
        payload.pop("details")
        return append_working_item(working_items, "plan_execution_error", payload)


def _append_plan_prepared(working_items, prepared):
    steps = prepared.get("steps") if isinstance(prepared, dict) else None
    if not isinstance(steps, list) or not steps or len(steps) > 5:
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    if any(not isinstance(step, dict) for step in steps):
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    proposals = [item for item in working_items if item.kind == "plan_step_proposed"]
    if len(proposals) < len(steps):
        raise EmbeddedRuntimeError("agent_working_transcript_invalid")
    proposals = proposals[-len(steps):]
    call_ids = []
    capabilities = []
    for proposal, step in zip(proposals, steps, strict=True):
        call_id = proposal.data.get("call_id")
        capability = proposal.data.get("capability")
        arguments = proposal.data.get("arguments")
        if (
            not isinstance(call_id, str)
            or not isinstance(capability, str)
            or not isinstance(arguments, dict)
        ):
            raise EmbeddedRuntimeError("agent_working_transcript_invalid")
        if (
            step.get("capability") != capability
            or step.get("arguments") != arguments
            or step.get("step_id") not in {None, call_id}
        ):
            raise EmbeddedRuntimeError("capability_plan_binding_mismatch")
        call_ids.append(call_id)
        capabilities.append(capability)
    return append_working_item(
        working_items,
        "plan_prepared",
        {
            "call_ids": call_ids,
            "capabilities": capabilities,
            "state": prepared.get("state"),
            "requires_confirmation": prepared.get("requires_confirmation") is True,
            "step_count": len(steps),
        },
    )


def _append_verified_effect_receipt(working_items, plan):
    if not isinstance(plan, dict):
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    steps = plan.get("steps")
    if plan.get("state") != "completed" or not isinstance(steps, list) or not steps:
        raise EmbeddedRuntimeError("capability_plan_corrupt")
    receipt_steps = []
    for step in steps:
        if not isinstance(step, dict):
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        result = step.get("result")
        verification = step.get("verification")
        step_state = step.get("state")
        if (
            step_state not in {"completed", "skipped"}
            or not isinstance(result, dict)
            or not isinstance(verification, dict)
            or step_state == "skipped"
            and (
                not isinstance(step.get("step_id"), str)
                or not _valid_skipped_receipt(result, verification)
            )
        ):
            raise EmbeddedRuntimeError("capability_plan_corrupt")
        receipt_steps.append(
            {
                "position": step.get("position"),
                "step_id": step.get("step_id"),
                "capability": step.get("capability"),
                "title": step.get("title"),
                "state": step_state,
                "result": dict(result),
                "verification": dict(verification),
            }
        )
    skipped_step_ids = [
        step["step_id"] for step in receipt_steps if step["state"] == "skipped"
    ]
    rich = {
        "verified": True,
        "plan_state": "completed",
        "step_count": len(receipt_steps),
        "skipped_step_count": len(skipped_step_ids),
        "skipped_step_ids": skipped_step_ids,
        "steps": receipt_steps,
    }
    compact = {
        "verified": True,
        "plan_state": "completed",
        "step_count": len(receipt_steps),
        "skipped_step_count": len(skipped_step_ids),
        "skipped_step_ids": skipped_step_ids,
        "details_omitted": True,
        "capabilities": [step["capability"] for step in receipt_steps],
        "steps": [_compact_receipt_step(step) for step in receipt_steps],
    }
    minimal = {
        "verified": True,
        "plan_state": "completed",
        "step_count": len(receipt_steps),
        "skipped_step_count": len(skipped_step_ids),
        "skipped_step_ids": skipped_step_ids,
        "details_omitted": True,
        "capabilities": [step["capability"] for step in receipt_steps],
        "steps": [_minimal_receipt_step(step) for step in receipt_steps],
    }
    baseline = None
    last_error = None
    for payload in (rich, compact, minimal):
        try:
            candidate = append_working_item(
                working_items,
                "verified_effect_receipt",
                payload,
            )
        except WorkingTranscriptError as error:
            if error.code not in {
                "agent_working_item_too_large",
                "agent_working_transcript_too_large",
            }:
                raise EmbeddedRuntimeError(error.code) from error
            last_error = error
            if error.code != "agent_working_transcript_too_large":
                continue
        else:
            if (
                working_transcript_bytes(candidate)
                <= MAX_TRANSCRIPT_BYTES - _POST_EFFECT_CONTINUATION_HEADROOM_BYTES
            ):
                return candidate
        if baseline is None:
            baseline = _post_effect_transcript_baseline(working_items)
        try:
            return append_working_item(
                baseline,
                "verified_effect_receipt",
                payload,
            )
        except WorkingTranscriptError as baseline_error:
            if baseline_error.code not in {
                "agent_working_item_too_large",
                "agent_working_transcript_too_large",
            }:
                raise EmbeddedRuntimeError(baseline_error.code) from baseline_error
            last_error = baseline_error
    raise EmbeddedRuntimeError(last_error.code) from last_error


def _post_effect_transcript_baseline(working_items):
    """Free bounded headroom while retaining the user's request and latest TaskPlan."""

    user_input = next(
        (item for item in working_items if item.kind == "user_input"),
        None,
    )
    if user_input is None:
        raise EmbeddedRuntimeError("agent_working_transcript_invalid")
    latest_task_plan = next(
        (item for item in reversed(working_items) if item.kind == "task_plan"),
        None,
    )
    retained = [user_input]
    if latest_task_plan is not None:
        retained.append(latest_task_plan)
    return tuple(
        WorkingItem(sequence, item.kind, dict(item.data))
        for sequence, item in enumerate(retained, 1)
    )


def _compact_receipt_step(step):
    return {
        "position": step["position"],
        "step_id": step["step_id"],
        "capability": step["capability"],
        "title": step["title"],
        "state": step["state"],
        "result": _compact_receipt_result(step["result"]),
        "verification": _compact_receipt_result(step["verification"]),
    }


def _minimal_receipt_step(step):
    return {
        "step_id": step["step_id"],
        "capability": step["capability"],
        "state": step["state"],
        "result": _minimal_receipt_result(step["result"]),
        "verification": _minimal_receipt_result(step["verification"]),
    }


def _minimal_receipt_result(value):
    compact = {
        key: value[key]
        for key in _COMPACT_RECEIPT_SCALARS
        if key in value and _compact_scalar(value[key])
    }
    dependencies = value.get("dependencies")
    if isinstance(dependencies, list):
        compact["dependencies"] = [
            {"step_id": item["step_id"], "outcome": item["outcome"]}
            for item in dependencies[:5]
            if isinstance(item, dict)
            and isinstance(item.get("step_id"), str)
            and isinstance(item.get("outcome"), str)
        ]
    return compact


def _compact_receipt_result(value):
    """Retain bounded business outcome evidence when the full receipt is too large."""

    compact = {
        key: value[key]
        for key in _COMPACT_RECEIPT_SCALARS
        if key in value and _compact_scalar(value[key])
    }
    for key in ("failed_record_ids", "excluded_record_ids"):
        record_ids = value.get(key)
        if not isinstance(record_ids, list):
            continue
        compact[f"{key}_sample"] = list(record_ids[:_COMPACT_RECEIPT_ID_SAMPLE])
        compact[f"{key}_omitted_count"] = max(
            0,
            len(record_ids) - _COMPACT_RECEIPT_ID_SAMPLE,
        )
    retained_groups = value.get("retained_groups")
    if isinstance(retained_groups, list):
        compact["retained_groups_sample"] = [
            _compact_retained_group(group)
            for group in retained_groups[:_COMPACT_RECEIPT_GROUP_SAMPLE]
            if isinstance(group, dict)
        ]
        compact["retained_groups_omitted_count"] = max(
            0,
            len(retained_groups) - _COMPACT_RECEIPT_GROUP_SAMPLE,
        )
    dependencies = value.get("dependencies")
    if isinstance(dependencies, list):
        compact["dependencies"] = [
            {"step_id": item["step_id"], "outcome": item["outcome"]}
            for item in dependencies[:5]
            if isinstance(item, dict)
            and isinstance(item.get("step_id"), str)
            and isinstance(item.get("outcome"), str)
        ]
    return compact


def _valid_skipped_receipt(result, verification):
    dependencies = result.get("dependencies")
    return (
        set(result) == {"outcome", "reason", "executed", "dependencies"}
        and result.get("outcome") == "skipped"
        and result.get("reason") == "dependency_incomplete"
        and result.get("executed") is False
        and isinstance(dependencies, list)
        and bool(dependencies)
        and len(dependencies) <= 5
        and all(
            isinstance(item, dict)
            and set(item) == {"step_id", "outcome"}
            and isinstance(item.get("step_id"), str)
            and item.get("outcome") in {"partial", "blocked", "skipped"}
            for item in dependencies
        )
        and verification == {"verified": True, **result}
    )


def _compact_retained_group(group):
    compact = {
        key: group[key]
        for key in (
            "state",
            "error_code",
            "message",
            "resolution",
            "blocking_model",
            "count",
        )
        if key in group and _compact_scalar(group[key])
    }
    record_ids = group.get("record_ids")
    if isinstance(record_ids, list):
        compact["record_ids_sample"] = list(
            record_ids[:_COMPACT_RECEIPT_GROUP_ID_SAMPLE]
        )
        compact["record_ids_omitted_count"] = max(
            0,
            len(record_ids) - _COMPACT_RECEIPT_GROUP_ID_SAMPLE,
        )
    return compact


def _compact_scalar(value):
    return (
        value is None
        or type(value) in {bool, int, float}
        or isinstance(value, str)
        and len(value) <= 512
    )
