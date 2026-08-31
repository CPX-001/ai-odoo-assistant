"""Disposable Odoo-shell runner for the Phase-6 recovery/journal real gates.

Execute with ``odoo-bin shell -d odoo_ai_*`` and set ``P6_PHASE2_GATE`` to
``atomicity``, ``segmented_setup``, ``segmented_resume`` or ``journal``.  The
runner refuses non-disposable databases and prints one JSON result.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime

from odoo import SUPERUSER_ID
from odoo.addons.odoo_ai_assistant.runtime.agent import (
    CapabilityPlanError,
    CapabilityPlanService,
    PlannedCapability,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities import (
    CapabilityApproval,
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityPolicy,
    CapabilityPreview,
    CapabilityRegistry,
    CapabilityResult,
    CapabilityRisk,
    CapabilityVerification,
    discover_capabilities,
)

env = globals()["env"]
gate = os.environ.get("P6_PHASE2_GATE", "").strip()
if not env.cr.dbname.startswith("odoo_ai_"):
    raise RuntimeError("Phase-6 real gates require a disposable odoo_ai_* database")


def effective_env():
    result = env(user=env.ref("base.user_admin").id, su=False)
    if result.su:
        raise AssertionError("effective Odoo environment must use su=False")
    return result


def screen(record_id=None):
    return {
        "action_id": None,
        "allowed_context_subset": {},
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "menu_id": None,
        "model": "res.partner",
        "res_id": record_id,
        "selected_ids": [],
        "view_type": "form" if record_id else "list",
    }


def context_for(user_env, turn_uuid):
    return CapabilityContext(
        env=user_env,
        turn_id=turn_uuid,
        screen=screen(),
        metadata={
            "capability_policy": {
                "confirmation_mode": "always_confirm",
                "max_auto_risk": "low",
                "max_provider_decisions": 12,
                "max_capability_calls": 8,
                "max_consecutive_correctable_failures": 3,
                "max_write_steps_per_plan": 12,
                "max_effect_steps_per_plan": 5,
            }
        },
    )


def services(user_env, turn_uuid, registry=None):
    registry = registry or discover_capabilities()
    context = context_for(user_env, turn_uuid)
    executor = CapabilityExecutor(
        registry,
        context,
        policy=CapabilityPolicy(),
        config=CapabilityConfigResolver(),
    )
    return registry, context, CapabilityPlanService(registry=registry, executor=executor)


def new_turn(user_env, marker, record_id=None):
    queued = user_env["odoo.ai.turn"].enqueue_for_current_user(
        message=marker,
        screen=screen(record_id),
        client_request_id=f"p6.phase2.{marker.lower().replace('_', '.')}.0001",
    )
    return user_env["odoo.ai.turn"]._owned_turn(queued["turn_id"])


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def fingerprint(record, requested):
    raw = json.dumps(
        {"id": record.id, "name": record.name, "requested": requested},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def recovery_registry():
    input_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["record_id", "value", "fail"],
        "properties": {
            "record_id": {"type": "integer", "minimum": 1},
            "value": {"type": "string", "minLength": 1, "maxLength": 160},
            "fail": {"type": "boolean"},
        },
    }
    output_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["model", "record_id", "name"],
        "properties": {
            "model": {"type": "string", "const": "res.partner"},
            "record_id": {"type": "integer", "minimum": 1},
            "name": {"type": "string"},
        },
    }

    def preview(ctx, args):
        record = ctx.env["res.partner"].browse(args["record_id"]).exists()
        if not record:
            raise CapabilityError("p6_fixture_target_missing")
        return CapabilityPreview(
            summary={
                "operation": "patch",
                "model": "res.partner",
                "record_id": record.id,
                "values": {"name": args["value"]},
            },
            precondition_fingerprint=fingerprint(record, args["value"]),
        )

    def execute(ctx, args):
        if args["fail"]:
            raise CapabilityError("p6_fixture_injected_failure")
        record = ctx.env["res.partner"].browse(args["record_id"]).exists()
        record.write({"name": args["value"]})
        return CapabilityResult(
            data={"model": "res.partner", "record_id": record.id, "name": record.name}
        )

    def verify(ctx, args):
        record = ctx.env["res.partner"].browse(args["record_id"]).exists()
        return CapabilityVerification(
            verified=bool(record and record.name == args["value"]),
            summary={"model": "res.partner", "record_id": args["record_id"]},
        )

    common = {
        "description": "Disposable trusted recovery gate capability.",
        "input_schema": input_schema,
        "output_schema": output_schema,
        "risk": CapabilityRisk.WRITE,
        "approval": CapabilityApproval.ALWAYS,
        "exposure": CapabilityExposure.PLAN,
        "handler": execute,
        "preview_handler": preview,
        "verify_handler": verify,
        "max_calls": 4,
    }
    segmented = CapabilityDefinition(
        name="p6.fixture.segmented_patch",
        effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
        audit_metadata={
            "recovery_mode": "segmented",
            "journal_classification": "irreversible",
        },
        **common,
    )
    external = CapabilityDefinition(
        name="p6.fixture.external_patch",
        effect=CapabilityEffect.EXTERNAL,
        audit_metadata={
            "recovery_mode": "external",
            "journal_classification": "external_or_unknown",
        },
        **common,
    )
    return CapabilityRegistry((segmented, external))


def atomicity_gate():
    user_env = effective_env()
    first = user_env["res.partner"].create({"name": "P6 ATOMIC BEFORE A"})
    second = user_env["res.partner"].create({"name": "P6 ATOMIC BEFORE B"})
    first_id, second_id = first.id, second.id
    env.cr.commit()
    _registry, _context, plans = services(user_env, "p6-real-atomicity")
    prepared = asyncio.run(
        plans.prepare(
            (
                PlannedCapability(
                    "odoo.record.patch",
                    {"model": "res.partner", "record_id": first_id, "values": {"name": "P6 ATOMIC AFTER A"}},
                    "Patch A",
                    "atomic-a",
                ),
                PlannedCapability(
                    "odoo.record.patch",
                    {"model": "res.partner", "record_id": second_id, "values": {"name": "P6 ATOMIC AFTER B"}},
                    "Patch B",
                    "atomic-b",
                    ("atomic-a",),
                ),
            )
        )
    )
    assert prepared["recovery_units"] == [
        {
            "unit_id": "unit-1",
            "mode": "odoo_atomic",
            "step_ids": ["atomic-a", "atomic-b"],
            "state": "prepared",
        }
    ]
    try:
        executed = asyncio.run(
            plans.execute({**prepared, "state": "authorized"}, human_approved=True)
        )
        assert len(executed.results) == 2
        assert user_env["res.partner"].browse(first_id).name == "P6 ATOMIC AFTER A"
        assert user_env["res.partner"].browse(second_id).name == "P6 ATOMIC AFTER B"
        raise RuntimeError("p6_fixture_failure_before_transaction_completion")
    except RuntimeError as error:
        assert str(error) == "p6_fixture_failure_before_transaction_completion"
        env.cr.rollback()
    first = effective_env()["res.partner"].browse(first_id).exists()
    second = effective_env()["res.partner"].browse(second_id).exists()
    rolled_back = first.name == "P6 ATOMIC BEFORE A" and second.name == "P6 ATOMIC BEFORE B"
    assert rolled_back
    first.unlink()
    second.unlink()
    env.cr.commit()
    emit(
        {
            "gate": "P6-REAL-EFFECT-ATOMICITY",
            "result": "PASS",
            "steps": 2,
            "recovery_mode": "odoo_atomic",
            "injected_failure_before_commit": True,
            "all_business_writes_rolled_back": True,
            "effective_user_su_false": True,
        }
    )


def segmented_setup_gate():
    user_env = effective_env()
    records = user_env["res.partner"].create(
        [
            {"name": "P6 SEGMENT BEFORE"},
            {"name": "P6 EXTERNAL BEFORE"},
            {"name": "P6 FUTURE BEFORE"},
        ]
    )
    turn = new_turn(user_env, "P6_SEGMENTED_RECOVERY", records[0].id)
    turn_uuid = turn.turn_uuid
    turn.with_user(SUPERUSER_ID).write(
        {"state": "running", "lease_token": "p6-phase2-segmented", "write_barrier": True}
    )
    registry = recovery_registry()
    _registry, _context, plans = services(user_env, turn_uuid, registry)
    prepared = asyncio.run(
        plans.prepare(
            (
                PlannedCapability(
                    "p6.fixture.segmented_patch",
                    {"record_id": records[0].id, "value": "P6 SEGMENT COMPLETED", "fail": False},
                    "Complete durable segment",
                    "segment-completed",
                ),
                PlannedCapability(
                    "p6.fixture.external_patch",
                    {"record_id": records[1].id, "value": "P6 EXTERNAL NEVER", "fail": True},
                    "Inject external in-flight failure",
                    "external-inflight",
                    ("segment-completed",),
                ),
                PlannedCapability(
                    "p6.fixture.segmented_patch",
                    {"record_id": records[2].id, "value": "P6 FUTURE NEVER", "fail": False},
                    "Future segment",
                    "segment-future",
                    ("external-inflight",),
                ),
            )
        )
    )
    authorized = {**prepared, "state": "authorized"}
    journal = env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)
    envelope = {
        "format_version": 1,
        "answer": "",
        "confidence": "high",
        "human_approved": True,
        "plan": authorized,
    }
    turn.with_user(SUPERUSER_ID).write({"capability_plan_payload": envelope})
    env.cr.commit()

    def checkpoint(phase, snapshot, unit, is_last):
        del phase, unit, is_last
        current = {**envelope, "plan": snapshot}
        current_turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        journal._sync_plan(current_turn, snapshot)
        current_turn.with_user(SUPERUSER_ID).write({"capability_plan_payload": current})
        env.cr.commit()

    try:
        asyncio.run(
            plans.execute(
                authorized,
                human_approved=True,
                recovery_checkpoint=checkpoint,
            )
        )
    except CapabilityError as error:
        assert error.code == "p6_fixture_injected_failure"
    else:
        raise AssertionError("segmented failure was not injected")
    env.cr.rollback()
    user_env = effective_env()
    turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
    turn.with_user(SUPERUSER_ID).write({"state": "failed"})
    env.cr.commit()
    rows = env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID).search(
        [("turn_id", "=", turn.id)], order="id"
    )
    states = {row.step_id: row.state for row in rows}
    assert states == {
        "segment-completed": "verified",
        "external-inflight": "uncertain",
        "segment-future": "prepared",
    }
    assert user_env["res.partner"].browse(records[0].id).name == "P6 SEGMENT COMPLETED"
    assert user_env["res.partner"].browse(records[1].id).name == "P6 EXTERNAL BEFORE"
    assert user_env["res.partner"].browse(records[2].id).name == "P6 FUTURE BEFORE"
    emit(
        {
            "gate": "P6-REAL-SEGMENTED-RECOVERY",
            "stage": "failure_persisted",
            "result": "PASS",
            "turn_id": turn_uuid,
            "completed_prior_unit": True,
            "inflight_external_state": "uncertain",
            "future_unit_unexecuted": True,
        }
    )


def segmented_resume_gate():
    user_env = effective_env()
    turn = user_env["odoo.ai.turn"].search(
        [("input_message", "=", "P6_SEGMENTED_RECOVERY")], limit=1
    )
    if not turn:
        raise AssertionError("segmented setup turn missing")
    plan = turn.capability_plan_payload["plan"]
    registry = recovery_registry()
    _registry, _context, plans = services(user_env, turn.turn_uuid, registry)
    try:
        asyncio.run(plans.execute(plan, human_approved=True, recovery_checkpoint=lambda *_: None))
    except CapabilityPlanError as error:
        assert error.code == "capability_plan_recovery_required"
    else:
        raise AssertionError("persisted in-flight unit was replayed")
    ids = [step["arguments"]["record_id"] for step in plan["steps"]]
    records = user_env["res.partner"].browse(ids).exists()
    names = {record.id: record.name for record in records}
    assert names[ids[0]] == "P6 SEGMENT COMPLETED"
    assert names[ids[1]] == "P6 EXTERNAL BEFORE"
    assert names[ids[2]] == "P6 FUTURE BEFORE"
    rows = env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID).search(
        [("turn_id", "=", turn.id)], order="id"
    )
    assert [row.state for row in rows] == ["verified", "uncertain", "prepared"]
    records.unlink()
    turn.with_user(SUPERUSER_ID).unlink()
    env.cr.commit()
    emit(
        {
            "gate": "P6-REAL-SEGMENTED-RECOVERY",
            "stage": "fresh_worker_resume",
            "result": "PASS",
            "blind_replay_blocked": True,
            "completed_unit_preserved": True,
            "future_unit_unexecuted": True,
        }
    )


def execute_and_journal(user_env, turn, requested):
    registry, context, plans = services(user_env, turn.turn_uuid)
    prepared = asyncio.run(plans.prepare((requested,)))
    authorized = {**prepared, "state": "authorized"}
    journal = env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)
    journal._sync_plan(turn, authorized)
    executed = asyncio.run(plans.execute(authorized, human_approved=True))
    journal._sync_plan(turn, executed.payload)
    envelope = {
        "format_version": 1,
        "answer": "Effect completed.",
        "confidence": "high",
        "human_approved": True,
        "plan": executed.payload,
    }
    turn.with_user(SUPERUSER_ID).write(
        {
            "state": "completed",
            "write_barrier": True,
            "capability_plan_payload": envelope,
            "reversion_state": "available",
        }
    )
    response = user_env["odoo.ai.embedded.runtime"]._plan_response(
        turn,
        envelope,
        {"confirmation_mode": "always_confirm", "max_auto_risk": "low", "allow_synthetic_data": False},
    )
    turn.with_user(SUPERUSER_ID).write({"result_payload": response})
    return registry, context, executed


def journal_gate():
    user_env = effective_env()
    patch_target = user_env["res.partner"].create({"name": "P6 JOURNAL BEFORE"})
    delete_target = user_env["res.partner"].create({"name": "P6 JOURNAL DELETE"})
    turns = []
    patch_turn = new_turn(user_env, "P6_JOURNAL_PATCH", patch_target.id)
    turns.append(patch_turn)
    _registry, _context, _patch_execution = execute_and_journal(
        user_env,
        patch_turn,
        PlannedCapability(
            "odoo.record.patch",
            {"model": "res.partner", "record_id": patch_target.id, "values": {"name": "P6 JOURNAL AFTER"}},
            "Journal patch",
            "journal-patch",
        ),
    )
    create_turn = new_turn(user_env, "P6_JOURNAL_CREATE")
    turns.append(create_turn)
    _registry, _context, create_execution = execute_and_journal(
        user_env,
        create_turn,
        PlannedCapability(
            "odoo.record.create",
            {"model": "res.partner", "values": {"name": "P6 JOURNAL CREATED"}},
            "Journal create",
            "journal-create",
        ),
    )
    created_id = create_execution.results[0].data["record_id"]
    delete_turn = new_turn(user_env, "P6_JOURNAL_DELETE", delete_target.id)
    turns.append(delete_turn)
    _registry, _context, _delete_execution = execute_and_journal(
        user_env,
        delete_turn,
        PlannedCapability(
            "odoo.record.delete",
            {"model": "res.partner", "record_id": delete_target.id},
            "Journal delete",
            "journal-delete",
        ),
    )
    expected = {
        patch_turn.turn_uuid: "reversible",
        create_turn.turn_uuid: "reconstructable",
        delete_turn.turn_uuid: "irreversible",
    }
    projections = {}
    for turn in turns:
        projection = user_env["odoo.ai.turn"].effect_journal_for_current_user(turn.turn_uuid)
        assert projection["retention_days"] == 7
        assert len(projection["entries"]) == 1
        entry = projection["entries"][0]
        assert entry["classification"] == expected[turn.turn_uuid]
        assert entry["state"] == "verified"
        assert entry["target"]["model"] == "res.partner"
        assert all(
            key not in entry
            for key in ("before_payload", "after_payload", "receipt_payload")
        )
        projections[turn.turn_uuid] = entry
    assert projections[create_turn.turn_uuid]["reconstructable"] is True
    assert projections[create_turn.turn_uuid]["reversible"] is False
    reverted = user_env["odoo.ai.turn"].revert_for_current_user(patch_turn.turn_uuid)
    patch_target.invalidate_recordset(["name"])
    assert patch_target.name == "P6 JOURNAL BEFORE"
    assert reverted["response"]["plan"]["metadata"]["reversion_state"] == "completed"
    patch_row = env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID).search(
        [("turn_id", "=", patch_turn.id)], limit=1
    )
    assert patch_row.state == "reverted"
    user_env["res.partner"].browse([patch_target.id, created_id]).exists().unlink()
    env["odoo.ai.turn"].with_user(SUPERUSER_ID).browse([turn.id for turn in turns]).unlink()
    env.cr.commit()
    emit(
        {
            "gate": "P6-REAL-EFFECT-JOURNAL",
            "result": "PASS",
            "classifications": ["reversible", "reconstructable", "irreversible"],
            "raw_payloads_hidden": True,
            "retention_days": 7,
            "target_metadata_present": True,
            "reversible_row_reverted": True,
            "reconstructable_not_presented_as_undo": True,
            "effective_user_su_false": True,
        }
    )


if gate == "atomicity":
    atomicity_gate()
elif gate == "segmented_setup":
    segmented_setup_gate()
elif gate == "segmented_resume":
    segmented_resume_gate()
elif gate == "journal":
    journal_gate()
else:
    raise RuntimeError("P6_PHASE2_GATE must select a supported gate")
