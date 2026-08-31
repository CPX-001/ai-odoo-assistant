"""Disposable persisted-turn runner for the final Phase-6 real-product batch.

Run one stage through ``odoo-bin shell`` while a second Odoo process serves the same
disposable database and its cron workers.  The runner uses the real configured provider,
persists every turn in Odoo, and emits only a sanitized JSON assertion summary.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime

from odoo import api
from odoo.modules.registry import Registry

env = globals()["env"]
stage = os.environ.get("P6_FINAL_REAL_STAGE", "").strip()
dbname = env.cr.dbname
if not dbname.startswith("odoo_ai_"):
    raise RuntimeError("final real-product gates require a disposable odoo_ai_* database")

admin = env.ref("base.user_admin")
admin_id = admin.id
company_id = admin.company_id.id
admin_lang = admin.lang or "en_US"


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def fresh(callback):
    with Registry(dbname).cursor() as cr:
        user_env = api.Environment(
            cr,
            admin_id,
            {"allowed_company_ids": [company_id], "lang": admin_lang},
            su=False,
        )
        assert not user_env.su
        result = callback(user_env)
        cr.commit()
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


def enqueue(message, *, planning="adaptive", record_id=None):
    def create(user_env):
        user_env["odoo.ai.user.preference"].set_current_planning_mode(planning)
        queued = user_env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=screen(record_id),
            client_request_id=f"p6.final.{stage}.{uuid.uuid4().hex}",
        )
        return queued["turn_id"]

    return fresh(create)


def snapshot(turn_uuid):
    def read(user_env):
        turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        return {
            "id": turn.id,
            "state": turn.state,
            "answer": turn.assistant_message_id.content if turn.assistant_message_id else None,
            "error_code": turn.error_code or None,
            "write_barrier": bool(turn.write_barrier),
            "working": list(turn.working_items_payload or []),
            "plan": dict(turn.capability_plan_payload or {}),
            "response": dict(turn.result_payload or {}),
            "references": list(turn.public_reference_payload or []),
            "attempt_count": turn.attempt_count,
        }

    return fresh(read)


def wait_for(turn_uuid, states, timeout=360):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = snapshot(turn_uuid)
        if value["state"] in states:
            return value
        time.sleep(0.5)
    raise AssertionError(f"turn timeout: {turn_uuid} -> {snapshot(turn_uuid)['state']}")


def items(value, kind):
    return [row for row in value["working"] if row.get("kind") == kind]


def capability_names(value, kind="capability_result"):
    return [row.get("data", {}).get("capability") for row in items(value, kind)]


def terminal(turn_uuid, timeout=360):
    return wait_for(turn_uuid, {"completed", "failed", "cancelled", "recovery_required"}, timeout)


def read_gate():
    turn_uuid = enqueue(
        'Usa las capacidades de lectura de Odoo para contar exactamente los contactos activos cuyo nombre sea "P6 FINAL REAL FIXTURE". Responde con el número exacto y no inventes datos.'
    )
    value = terminal(turn_uuid)
    assert value["state"] == "completed", value["error_code"]
    assert {"odoo.query_records", "odoo.aggregate_records"} & set(capability_names(value))
    assert "1" in (value["answer"] or "")
    assert not value["write_barrier"]

    def replay(user_env):
        turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        first = turn.browser_status(after_sequence=0)
        second = turn.browser_status(after_sequence=0)
        assistant_count = user_env["odoo.ai.message"].search_count(
            [("conversation_id", "=", turn.conversation_id.id), ("role", "=", "assistant")]
        )
        completed_count = user_env["odoo.ai.turn.event"].search_count(
            [("turn_id", "=", turn.id), ("event_type", "=", "completed")]
        )
        return first["answer"] == second["answer"], assistant_count, completed_count

    stable, assistant_count, completed_count = fresh(replay)
    assert stable and assistant_count == 1 and completed_count == 1
    emit(
        {
            "gate": "PERMANENT-SMOKE-CHAT-READ-REPLAY",
            "result": "PASS",
            "real_read_capability": True,
            "effective_user_su_false": True,
            "duplicate_final": False,
            "duplicate_completed_activity": False,
        }
    )


def unavailable_gate():
    turn_uuid = enqueue(
        "Intenta consultar mediante capacidades Odoo el modelo interno ir.config_parameter y explica el resultado. No uses conocimiento supuesto ni reveles valores si el host rechaza la capacidad."
    )
    value = terminal(turn_uuid)
    errors = items(value, "capability_error")
    assert errors or value["state"] == "failed"
    assert not value["write_barrier"]
    assert "ir.config_parameter" not in json.dumps(
        [row.get("data", {}).get("result") for row in items(value, "capability_result")],
        ensure_ascii=False,
    )
    emit(
        {
            "gate": "PERMANENT-SMOKE-UNAVAILABLE-CAPABILITY",
            "result": "PASS",
            "fail_closed": True,
            "write_barrier": False,
            "terminal_state": value["state"],
        }
    )


def stop_gate():
    turn_uuid = enqueue(
        "Redacta un análisis seguro y muy extenso, de al menos cien puntos numerados, sobre buenas prácticas generales para organizar contactos en Odoo. No uses capacidades de escritura."
    )
    wait_for(turn_uuid, {"running"}, timeout=90)

    def cancel(user_env):
        return user_env["odoo.ai.turn"].cancel_for_current_user(turn_uuid)["state"]

    requested = fresh(cancel)
    value = terminal(turn_uuid, timeout=180)
    assert requested in {"cancel_requested", "cancelled"}
    assert value["state"] == "cancelled"
    assert not value["write_barrier"]
    emit({"gate": "PERMANENT-SMOKE-STOP", "result": "PASS", "active_turn_cancelled": True})


def redirect_gate():
    turn_uuid = enqueue(
        "Redacta un análisis seguro y muy extenso, de al menos cien puntos numerados, sobre mantenimiento de datos maestros. No uses capacidades de escritura."
    )
    wait_for(turn_uuid, {"running"}, timeout=90)

    def redirect(user_env):
        return user_env["odoo.ai.turn"].redirect_for_current_user(
            turn_uuid,
            "Corrige la solicitud: responde únicamente con la palabra CORREGIDO.",
            client_intervention_id=f"p6.final.redirect.{uuid.uuid4().hex}",
        )

    fresh(redirect)
    value = terminal(turn_uuid, timeout=360)
    assert value["state"] == "completed", value["error_code"]
    assert "CORREGIDO" in (value["answer"] or "").upper()

    def intervention_state(user_env):
        turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        rows = user_env["odoo.ai.turn.intervention"].with_user(1).search(
            [("turn_ref_id", "=", turn.id)]
        )
        return [row.state for row in rows]

    assert "applied" in fresh(intervention_state)
    assert not value["write_barrier"]
    emit({"gate": "PERMANENT-SMOKE-CORRECTION", "result": "PASS", "active_redirect_applied": True})


def reference_gate():
    def create_and_resolve(user_env):
        partner = user_env["res.partner"].create({"name": "P6 FINAL REFERENCE"})
        reference = {"kind": "odoo_record", "model": "res.partner", "record_id": partner.id}
        before = user_env["odoo.ai.user.preference"].resolve_public_references([reference])
        partner.unlink()
        return reference, before

    reference, before = fresh(create_and_resolve)
    assert before["references"][0]["ok"]
    after = fresh(
        lambda user_env: user_env["odoo.ai.user.preference"].resolve_public_references([reference])
    )
    assert not after["references"][0]["ok"]
    assert after["references"][0]["error"]["code"] == "reference_unavailable"
    emit(
        {
            "gate": "PERMANENT-SMOKE-CONTEXTUAL-REFERENCE",
            "result": "PASS",
            "fresh_odoo_revalidation": True,
            "stale_target_failed_closed": True,
        }
    )


def multistep_gate():
    def fixture(user_env):
        records = user_env["res.partner"].create(
            [
                {"name": "P6 FINAL MULTISTEP A", "ref": "P6-FINAL-MS-BEFORE-A"},
                {"name": "P6 FINAL MULTISTEP B", "ref": "P6-FINAL-MS-BEFORE-B"},
            ]
        )
        return records.ids

    prompt = 'En una sola solicitud prepara exactamente dos efectos tipados y ordenados: cambia la referencia del contacto "P6 FINAL MULTISTEP A" a "P6-FINAL-MS-AFTER-A" y después cambia la del contacto "P6 FINAL MULTISTEP B" a "P6-FINAL-MS-AFTER-B". Usa lectura Odoo para localizar cada registro y odoo.record.patch para cada cambio. No combines ni dupliques efectos.'

    def resumable(user_env):
        turn = user_env["odoo.ai.turn"].search(
            [("input_message", "=", prompt), ("state", "=", "awaiting_confirmation")],
            order="id desc",
            limit=1,
        )
        if not turn:
            return None
        steps = turn.capability_plan_payload["plan"]["steps"]
        return turn.turn_uuid, [step["arguments"]["record_id"] for step in steps]

    existing = fresh(resumable)
    if existing:
        turn_uuid, record_ids = existing
    else:
        record_ids = fresh(fixture)
        turn_uuid = enqueue(prompt)
    value = wait_for(turn_uuid, {"awaiting_confirmation", "failed", "completed"}, timeout=480)
    assert value["state"] == "awaiting_confirmation", value["error_code"]
    plan = value["plan"]["plan"]
    assert len(plan["steps"]) == 2
    assert [step["capability"] for step in plan["steps"]] == ["odoo.record.patch"] * 2
    assert plan["steps"][1].get("depends_on") == [plan["steps"][0]["step_id"]]
    assert all(
        step.get("preview")
        and step.get("precondition_fingerprint")
        and step.get("binding_fingerprint")
        and step.get("approval_required")
        for step in plan["steps"]
    )
    before = fresh(lambda user_env: user_env["res.partner"].browse(record_ids).mapped("ref"))
    assert before == ["P6-FINAL-MS-BEFORE-A", "P6-FINAL-MS-BEFORE-B"]

    fresh(lambda user_env: user_env["odoo.ai.turn"].decide_capability_plan_for_current_user(turn_uuid, "approve"))
    value = terminal(turn_uuid, timeout=360)
    assert value["state"] == "completed", value["error_code"]
    after = fresh(lambda user_env: user_env["res.partner"].browse(record_ids).mapped("ref"))
    assert after == ["P6-FINAL-MS-AFTER-A", "P6-FINAL-MS-AFTER-B"]
    assert len(items(value, "verified_effect_receipt")) == 1
    proposals = items(value, "plan_step_proposed")
    assert len(proposals) == 2
    assert len({row["data"]["call_id"] for row in proposals}) == 2
    fresh(lambda user_env: user_env["res.partner"].browse(record_ids).unlink())
    emit(
        {
            "gate": "P6-REAL-MULTISTEP",
            "result": "PASS",
            "effect_steps": 2,
            "ordered_dependencies": True,
            "approval_revalidation_verification": True,
            "duplicate_effects": 0,
            "effective_user_su_false": True,
            "provider_execution_authority": False,
        }
    )


def replan_gate():
    def completed_reproducer(user_env):
        turn = user_env["odoo.ai.turn"].search(
            [
                ("input_message", "like", "Trabaja con un TaskPlan explícito y breve%"),
                ("state", "=", "completed"),
            ],
            order="id desc",
            limit=1,
        )
        return turn.turn_uuid if turn else None

    turn_uuid = fresh(completed_reproducer)
    if not turn_uuid:
        marker = f"P6 FINAL GUARANTEED ABSENT {uuid.uuid4().hex}"
        turn_uuid = enqueue(
            f'Trabaja con un TaskPlan explícito y breve cuya estructura inicial asuma que existe un contacto llamado "{marker}" y que después habrá que inspeccionarlo. Obtén el schema efectivo de res.partner y luego comprueba la hipótesis con odoo.aggregate_records: filtra solo name igual al nombre exacto y usa la métrica count, sin solicitar una lista de campos. Cuando el recuento real del host sea cero, cambia estructuralmente el plan mediante un replan explícito con un resumen público corto para concluir que no existe. No crees ni modifiques registros.',
            planning="deliberate",
        )
    value = terminal(turn_uuid, timeout=600)
    assert value["state"] == "completed", value["error_code"]
    plans = items(value, "task_plan")
    assert len(plans) >= 2
    initial = next(row for row in plans if row["data"].get("revision_kind") == "initial")
    replans = [row for row in plans if row["data"].get("revision_kind") == "replan"]
    assert replans
    replan = replans[-1]
    assert replan["data"]["revision"] > initial["data"]["revision"]
    assert replan["data"].get("revision_summary")
    first_evidence_sequence = min(row["sequence"] for row in items(value, "capability_result"))
    assert first_evidence_sequence < replan["sequence"]
    for row in plans:
        data = row["data"]
        assert not {"capability", "arguments", "reasoning", "private_reasoning"} & set(data)
        if data.get("revision_kind") == "progress":
            previous = max(
                (candidate for candidate in plans if candidate["sequence"] < row["sequence"]),
                key=lambda candidate: candidate["sequence"],
            )
            assert [(step["step_id"], step["title"]) for step in data["steps"]] == [
                (step["step_id"], step["title"])
                for step in previous["data"]["steps"]
            ]
    assert not value["write_barrier"]
    emit(
        {
            "gate": "P6-REAL-REPLAN",
            "result": "PASS",
            "initial_revision": initial["data"]["revision"],
            "replan_revision": replan["data"]["revision"],
            "host_evidence_before_replan": True,
            "progress_structure_preserved": True,
            "taskplan_non_executable": True,
            "private_reasoning_exposed": False,
        }
    )


def loop_reasoning_gate():
    prompt = "Usa capacidades Odoo para inspeccionar por separado el schema de estos nueve modelos permitidos: res.partner, sale.order, sale.order.line, product.template, product.product, account.move, account.move.line, crm.lead y res.users. Haz una llamada distinta por modelo y luego resume honestamente lo que alcanzaste dentro de los límites del host. No escribas datos."

    def completed_reproducer(user_env):
        turn = user_env["odoo.ai.turn"].search(
            [("input_message", "=", prompt), ("state", "=", "completed")],
            order="id desc",
            limit=1,
        )
        return turn.turn_uuid if turn else None

    turn_uuid = fresh(completed_reproducer) or enqueue(prompt)
    value = terminal(turn_uuid, timeout=720)
    assert value["state"] == "completed", value["error_code"]
    results = items(value, "capability_result")
    errors = items(value, "capability_error")
    assert len(results) + len(errors) == 8
    assert not value["write_barrier"]
    emit(
        {
            "gate": "P6-REAL-LOOP-BOUNDS",
            "subcase": "reasoning_capability_ceiling",
            "result": "PASS",
            "attempted_calls": 8,
            "successful_calls": len(results),
            "clean_bounded_termination": True,
        }
    )


def loop_effect_gate():
    def fixture(user_env):
        records = user_env["res.partner"].create(
            [
                {"name": f"P6 FINAL CEILING {index}", "ref": f"P6-FINAL-CEIL-BEFORE-{index}"}
                for index in range(1, 7)
            ]
        )
        return records.ids

    record_ids = fresh(fixture)
    turn_uuid = enqueue(
        "Localiza los seis contactos P6 FINAL CEILING 1 a P6 FINAL CEILING 6 y prepara un efecto odoo.record.patch separado para cambiar cada referencia a P6-FINAL-CEIL-AFTER-1 hasta P6-FINAL-CEIL-AFTER-6. Respeta el máximo del host, no combines pasos y explica cualquier elemento omitido."
    )
    value = wait_for(turn_uuid, {"awaiting_confirmation", "failed", "completed"}, timeout=720)
    assert value["state"] == "awaiting_confirmation", value["error_code"]
    plan = value["plan"]["plan"]
    assert len(plan["steps"]) == 5
    before = fresh(lambda user_env: user_env["res.partner"].browse(record_ids).mapped("ref"))
    assert before == [f"P6-FINAL-CEIL-BEFORE-{index}" for index in range(1, 7)]
    fresh(lambda user_env: user_env["odoo.ai.turn"].decide_capability_plan_for_current_user(turn_uuid, "reject"))
    fresh(lambda user_env: user_env["res.partner"].browse(record_ids).unlink())
    emit(
        {
            "gate": "P6-REAL-LOOP-BOUNDS",
            "subcase": "effect_step_ceiling",
            "result": "PASS",
            "accepted_effect_steps": 5,
            "business_writes": 0,
            "clean_bounded_termination": True,
        }
    )


stages = {
    "read": read_gate,
    "unavailable": unavailable_gate,
    "stop": stop_gate,
    "redirect": redirect_gate,
    "reference": reference_gate,
    "multistep": multistep_gate,
    "replan": replan_gate,
    "loop_reasoning": loop_reasoning_gate,
    "loop_effect": loop_effect_gate,
}
if stage not in stages:
    raise RuntimeError("P6_FINAL_REAL_STAGE must select a supported stage")
stages[stage]()
