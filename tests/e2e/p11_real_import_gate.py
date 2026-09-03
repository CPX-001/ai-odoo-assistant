"""Real Odoo/Codex acceptance gates for Phase-11 durable CSV imports.

Run through ``odoo-bin shell`` against a disposable ``odoo_ai_p11_real_*``
database while an independent Odoo process serves turn and import cron workers.
The output contains only sanitized counters, fingerprints and timings.
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import odoo
from odoo import SUPERUSER_ID, Command, api
from odoo.addons.odoo_ai_assistant.models.data_import import DataImportWorkflowError
from odoo.modules.registry import Registry

env = globals()["env"]
DBNAME = env.cr.dbname
if not DBNAME.startswith("odoo_ai_p11_real_"):
    raise RuntimeError("P11 real gates require a disposable odoo_ai_p11_real_* database")

CODEX_EXECUTABLE = os.environ.get("P11_CODEX_EXECUTABLE", "").strip()
TESTED_SHA = os.environ.get("P11_TESTED_SHA", "").strip()
if not CODEX_EXECUTABLE:
    raise RuntimeError("P11_CODEX_EXECUTABLE is required")
if len(TESTED_SHA) != 40:
    raise RuntimeError("P11_TESTED_SHA must be the exact 40-character commit SHA")

ADMIN_ID = env.ref("base.user_admin").id
COMPANY_ID = env.company.id
RUN_ID = uuid.uuid4().hex[:10]
TERMINAL_TURNS = {"completed", "failed", "cancelled", "recovery_required"}
TERMINAL_IMPORTS = {"completed", "partial", "failed"}


def fresh(uid: int, callback: Callable, *, su: bool = False):
    with Registry(DBNAME).cursor() as cr:
        user_env = api.Environment(
            cr,
            uid,
            {"allowed_company_ids": [COMPANY_ID], "lang": "en_US"},
            su=su,
        )
        if not su:
            assert not user_env.su
        result = callback(user_env)
        cr.commit()
        user_env.registry.signal_changes()
        return result


def configure() -> tuple[int, int]:
    def apply(admin_env):
        admin_env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.codex_executable",
            CODEX_EXECUTABLE,
        )
        internal = admin_env.ref("base.group_user")
        partner_manager = admin_env.ref("base.group_partner_manager")
        importer = admin_env["res.users"].create(
            {
                "name": f"P11 Real Importer {RUN_ID}",
                "login": f"p11-real-importer-{RUN_ID}",
                "company_id": COMPANY_ID,
                "company_ids": [Command.set([COMPANY_ID])],
                "groups_id": [Command.set([internal.id, partner_manager.id])],
            }
        )
        denied = admin_env["res.users"].create(
            {
                "name": f"P11 Real Denied {RUN_ID}",
                "login": f"p11-real-denied-{RUN_ID}",
                "company_id": COMPANY_ID,
                "company_ids": [Command.set([COMPANY_ID])],
                "groups_id": [Command.set([internal.id])],
            }
        )
        return importer.id, denied.id

    importer_id, denied_id = fresh(ADMIN_ID, apply)
    fresh(
        importer_id,
        lambda user_env: user_env[
            "odoo.ai.user.preference"
        ].set_current_agent_profile("full_access"),
    )
    return importer_id, denied_id


def screen() -> dict[str, object]:
    return {
        "action_id": None,
        "allowed_context_subset": {},
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "menu_id": None,
        "model": "res.partner",
        "res_id": None,
        "selected_ids": [],
        "view_type": "list",
    }


def enqueue_with_csv(uid: int, *, filename: str, csv_text: str, prompt: str):
    def create(user_env):
        attachment = user_env["odoo.ai.knowledge.attachment"].create_upload(
            filename=filename,
            mimetype="text/csv",
            data=base64.b64encode(csv_text.encode()),
        )
        queued = user_env["odoo.ai.turn"].enqueue_for_current_user(
            message=f"{prompt}\n[[odoo_ai_attachment:{attachment.token}]]",
            screen=screen(),
            conversation_uuid=None,
            client_request_id=f"p11.real.{uuid.uuid4().hex}",
            planning_mode="adaptive",
        )
        return queued["turn_id"], attachment.id

    return fresh(uid, create)


def enqueue(uid: int, prompt: str) -> str:
    return fresh(
        uid,
        lambda user_env: user_env["odoo.ai.turn"].enqueue_for_current_user(
            message=prompt,
            screen=screen(),
            conversation_uuid=None,
            client_request_id=f"p11.real.{uuid.uuid4().hex}",
            planning_mode="adaptive",
        )["turn_id"],
    )


def turn_snapshot(uid: int, turn_uuid: str) -> dict[str, object]:
    def read(user_env):
        turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        answer = turn.assistant_message_id.content if turn.assistant_message_id else ""
        return {
            "state": turn.state,
            "answer": answer or "",
            "error_code": turn.error_code or "",
            "plan": dict(turn.capability_plan_payload or {}),
            "working": list(turn.working_items_payload or []),
        }

    return fresh(uid, read)


def capability_names(snapshot: dict[str, object]) -> set[str]:
    names = set()
    envelope = snapshot.get("plan")
    plan = envelope.get("plan") if isinstance(envelope, dict) else None
    for step in plan.get("steps", []) if isinstance(plan, dict) else []:
        if isinstance(step, dict) and isinstance(step.get("capability"), str):
            names.add(step["capability"])
    for item in snapshot.get("working", []):
        data = item.get("data") if isinstance(item, dict) else None
        capability = data.get("capability") if isinstance(data, dict) else None
        if isinstance(capability, str):
            names.add(capability)
    return names


def wait_turn(uid: int, turn_uuid: str) -> tuple[dict[str, object], int]:
    approvals = 0
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        value = turn_snapshot(uid, turn_uuid)
        if value["state"] == "awaiting_confirmation":
            fresh(
                uid,
                lambda user_env: user_env[
                    "odoo.ai.turn"
                ].decide_capability_plan_for_current_user(turn_uuid, "approve"),
            )
            approvals += 1
            continue
        if value["state"] in TERMINAL_TURNS:
            assert value["state"] == "completed", value["error_code"]
            lowered = str(value["answer"]).casefold()
            assert not any(
                token in lowered
                for token in ("access_token", "raw_reasoning", "refresh_token", "stderr")
            )
            return value, approvals
        time.sleep(0.5)
    raise AssertionError("p11_real_turn_timeout")


def session_snapshot(uid: int, session_uuid: str) -> dict[str, object]:
    return fresh(
        uid,
        lambda user_env: user_env[
            "odoo.ai.data.import.session"
        ].status_for_current_user(session_uuid, recent_chunks=20),
    )


def session_for_turn(uid: int, turn_uuid: str) -> str:
    def find(user_env):
        turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
        session = user_env["odoo.ai.data.import.session"].search(
            [("turn_id", "=", turn.id)],
            limit=1,
        )
        assert session, "assistant.data_import start capability did not create a session"
        return session.session_uuid

    return fresh(uid, find)


def wait_import(uid: int, session_uuid: str) -> dict[str, object]:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        value = session_snapshot(uid, session_uuid)
        if value["state"] in TERMINAL_IMPORTS:
            return value
        time.sleep(0.25)
    raise AssertionError("p11_real_import_timeout")


def run_csv_turn(
    uid: int,
    *,
    filename: str,
    csv_text: str,
    prompt: str,
) -> tuple[str, int, dict[str, object], int, float]:
    started = time.monotonic()
    turn_uuid, attachment_id = enqueue_with_csv(
        uid,
        filename=filename,
        csv_text=csv_text,
        prompt=prompt,
    )
    snapshot, approvals = wait_turn(uid, turn_uuid)
    return turn_uuid, attachment_id, snapshot, approvals, time.monotonic() - started


def assert_partner_count(uid: int, domain, expected: int) -> None:
    count = fresh(uid, lambda user_env: user_env["res.partner"].search_count(domain))
    assert count == expected, (domain, count, expected)


def set_import_cron(active: bool) -> None:
    def apply(admin_env):
        cron = admin_env.ref("odoo_ai_assistant.ir_cron_assistant_data_import")
        cron.write({"active": active})
        if active:
            cron._trigger()

    fresh(ADMIN_ID, apply)


def process_one_committed() -> bool:
    return fresh(
        SUPERUSER_ID,
        lambda system_env: system_env[
            "odoo.ai.data.import.session"
        ]._cron_process_pending(),
        su=True,
    )


def simulate_precommit_loss(session_uuid: str) -> None:
    with Registry(DBNAME).cursor() as cr:
        system_env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        session = system_env["odoo.ai.data.import.session"].search(
            [("session_uuid", "=", session_uuid)],
            limit=1,
        )
        assert session and session.state == "queued"
        before_ids = set(
            system_env["res.partner"].search(
                [("email", "like", f"p11-interrupt-{RUN_ID}-%")]
            ).ids
        )
        session._process_one_chunk()
        assert session.next_row > 0
        assert session.chunk_ids
        cr.rollback()

    def verify(system_env):
        session = system_env["odoo.ai.data.import.session"].search(
            [("session_uuid", "=", session_uuid)],
            limit=1,
        )
        after_ids = set(
            system_env["res.partner"].search(
                [("email", "like", f"p11-interrupt-{RUN_ID}-%")]
            ).ids
        )
        assert session.state == "queued"
        assert session.next_row == 0
        assert session.chunk_count == 0
        assert not session.chunk_ids
        assert after_ids == before_ids

    fresh(SUPERUSER_ID, verify, su=True)


def assert_acl_denial(denied_id: int) -> None:
    turn_uuid, attachment_id = enqueue_with_csv(
        denied_id,
        filename="p11-denied.csv",
        csv_text=f"name,email\nP11 Denied,p11-denied-{RUN_ID}@example.test\n",
        prompt="Inspect this CSV for a contact import, but do not invent access.",
    )

    def inspect(user_env):
        try:
            user_env["odoo.ai.data.import.session"].inspect_csv_attachment(
                turn_uuid=turn_uuid,
                attachment_id=attachment_id,
                target_model="res.partner",
            )
        except DataImportWorkflowError as error:
            assert error.code == "data_import_create_access_denied", error.code
            return
        raise AssertionError("P11 ACL gate unexpectedly allowed contact creation")

    fresh(denied_id, inspect)


def environment_versions() -> dict[str, str]:
    def read(system_env):
        system_env.cr.execute("SHOW server_version")
        return {
            "odoo": odoo.release.version,
            "postgresql": system_env.cr.fetchone()[0],
        }

    return fresh(SUPERUSER_ID, read, su=True)


importer_id, denied_id = configure()
assert_acl_denial(denied_id)

# Normal product-path import.
small_emails = [
    f"p11-small-{RUN_ID}-a@example.test",
    f"p11-small-{RUN_ID}-b@example.test",
]
small_turn, _small_attachment, small_snapshot, small_approvals, small_turn_seconds = (
    run_csv_turn(
        importer_id,
        filename="p11-small.csv",
        csv_text=(
            "name,email\n"
            f"P11 Small A {RUN_ID},{small_emails[0]}\n"
            f"P11 Small B {RUN_ID},{small_emails[1]}\n"
        ),
        prompt=(
            "Importa este CSV en contactos (modelo res.partner). Usa primero "
            "assistant.data_import.inspect_csv y después assistant.data_import.start_csv. "
            "Mapea exactamente la columna 0 a name y la 1 a email, usa chunks de 1, "
            "ejecuta el plan y no añadas otros campos."
        ),
    )
)
assert "assistant.data_import.start_csv" in capability_names(small_snapshot)
small_session = session_for_turn(importer_id, small_turn)
small_status = wait_import(importer_id, small_session)
assert small_status["state"] == "completed", small_status
assert small_status["imported_rows"] == 2
assert small_status["failed_rows"] == 0
assert small_status["chunk_count"] == 2
assert small_status["planned_chunk_count"] == 2
assert all(chunk["receipt_fingerprint"] for chunk in small_status["chunks"])
assert_partner_count(importer_id, [("email", "in", small_emails)], 2)

# Realistically large staged import with several bounded chunks.
large_rows = 1_200
large_csv = "name,email\n" + "".join(
    f"P11 Large {RUN_ID} {index},p11-large-{RUN_ID}-{index}@example.test\n"
    for index in range(large_rows)
)
large_started = time.monotonic()
large_turn, _large_attachment, large_snapshot, large_approvals, large_turn_seconds = (
    run_csv_turn(
        importer_id,
        filename="p11-large.csv",
        csv_text=large_csv,
        prompt=(
            "Importa completamente este CSV grande en res.partner. Inspecciónalo con "
            "assistant.data_import.inspect_csv y usa assistant.data_import.start_csv con "
            "el mapeo exacto columna 0 -> name, columna 1 -> email y chunk_size 200. "
            "Ejecuta el plan create-only sin añadir campos."
        ),
    )
)
assert "assistant.data_import.start_csv" in capability_names(large_snapshot)
large_session = session_for_turn(importer_id, large_turn)
large_status = wait_import(importer_id, large_session)
large_total_seconds = time.monotonic() - large_started
assert large_status["state"] == "completed", large_status
assert large_status["total_rows"] == large_rows
assert large_status["imported_rows"] == large_rows
assert large_status["chunk_count"] == 6
assert large_status["planned_chunk_count"] == 6
assert all(chunk["input_count"] <= 200 for chunk in large_status["chunks"])
assert_partner_count(
    importer_id,
    [("email", "like", f"p11-large-{RUN_ID}-%")],
    large_rows,
)

# Ambiguous headers, explicit safe remapping and deterministic cleanup.
clean_email = f"p11-clean-{RUN_ID}@example.test"
clean_turn, clean_attachment, clean_snapshot, clean_approvals, clean_turn_seconds = (
    run_csv_turn(
        importer_id,
        filename="p11-ambiguous-clean.csv",
        csv_text=(
            "Contact label,Mailbox,company_id\n"
            f"  P11    Clean {RUN_ID}  ,,{COMPANY_ID}\n"
        ),
        prompt=(
            "Inspecciona este CSV ambiguo para res.partner. Corrige el mapeo de forma "
            "explícita: columna 0 -> name, columna 1 -> email e ignora por completo la "
            "columna 2 company_id. Usa assistant.data_import.inspect_cleanup y luego "
            "assistant.data_import.start_clean_csv con normalize_whitespace para name y "
            f"set_if_empty={clean_email} para email, chunk_size 1. Ejecuta el plan."
        ),
    )
)
assert "assistant.data_import.start_clean_csv" in capability_names(clean_snapshot)
clean_session = session_for_turn(importer_id, clean_turn)
clean_status = wait_import(importer_id, clean_session)
assert clean_status["state"] == "completed", clean_status
assert clean_status["imported_rows"] == 1
assert clean_status["corrected_rows"] == 1


def validate_cleanup_authority(user_env):
    session = user_env["odoo.ai.data.import.session"].search(
        [("session_uuid", "=", clean_session)],
        limit=1,
    )
    assert [item["field"] for item in session.mapping_json] == ["name", "email"]
    assert session.cleanup_fingerprint
    partner = user_env["res.partner"].search([("email", "=", clean_email)], limit=1)
    assert partner.name == f"P11 Clean {RUN_ID}"
    try:
        user_env["odoo.ai.data.import.session"]._prepare_cleanup_request(
            turn_uuid=clean_turn,
            attachment_id=clean_attachment,
            target_model="res.partner",
            mapping=[
                {"column_index": 0, "field": "name"},
                {"column_index": 2, "field": "company_id"},
            ],
            cleanup_rules=[
                {
                    "field": "company_id",
                    "operation": "replace_exact",
                    "match": str(COMPANY_ID),
                    "value": "1",
                }
            ],
        )
    except DataImportWorkflowError as error:
        assert error.code in {
            "data_import_mapping_invalid",
            "data_import_cleanup_invalid",
        }
        return session.cleanup_fingerprint
    raise AssertionError("cleanup widened authority to company_id")


cleanup_fingerprint = fresh(importer_id, validate_cleanup_authority)

# Partial rejection through the real Assistant, then real Assistant repair/resume.
partial_turn, _partial_attachment, partial_snapshot, partial_approvals, partial_seconds = (
    run_csv_turn(
        importer_id,
        filename="p11-partial.csv",
        csv_text=(
            "name,type\n"
            f"P11 Partial Valid {RUN_ID},contact\n"
            f"P11 Partial Repair {RUN_ID},not_a_partner_type\n"
        ),
        prompt=(
            "Importa este CSV en res.partner usando assistant.data_import.inspect_csv y "
            "assistant.data_import.start_csv. Mapea exactamente columna 0 -> name y "
            "columna 1 -> type, usa chunk_size 1 y ejecuta el plan. No corrijas valores "
            "antes de esta primera importación."
        ),
    )
)
assert "assistant.data_import.start_csv" in capability_names(partial_snapshot)
partial_session = session_for_turn(importer_id, partial_turn)
partial_status = wait_import(importer_id, partial_session)
assert partial_status["state"] == "partial", partial_status
assert partial_status["imported_rows"] == 1
assert partial_status["failed_rows"] == 1
assert partial_status["remaining_rows"] == 0
assert [chunk["state"] for chunk in partial_status["chunks"]] == [
    "completed",
    "rejected",
]
assert not partial_status["chunks"][1]["record_ids"]
assert_partner_count(
    importer_id,
    [("name", "=", f"P11 Partial Valid {RUN_ID}")],
    1,
)
assert_partner_count(
    importer_id,
    [("name", "=", f"P11 Partial Repair {RUN_ID}")],
    0,
)

repair_turn = enqueue(
    importer_id,
    (
        "Inspecciona el rechazo de la sesión "
        f"{partial_session} con assistant.data_import.inspect_rejected. Después usa "
        "assistant.data_import.resume_csv para corregir exactamente la fila 2, campo "
        "type, al valor contact. Ejecuta el plan y no modifiques ninguna otra fila o campo."
    ),
)
repair_snapshot, repair_approvals = wait_turn(importer_id, repair_turn)
assert "assistant.data_import.resume_csv" in capability_names(repair_snapshot)
repaired_status = wait_import(importer_id, partial_session)
assert repaired_status["state"] == "completed", repaired_status
assert repaired_status["imported_rows"] == 2
assert repaired_status["failed_rows"] == 0
assert repaired_status["corrected_rows"] == 1
assert repaired_status["chunk_count"] == 3
assert repaired_status["planned_chunk_count"] == 3
assert [chunk["state"] for chunk in repaired_status["chunks"]] == [
    "completed",
    "rejected",
    "completed",
]
assert_partner_count(
    importer_id,
    [("name", "in", [f"P11 Partial Valid {RUN_ID}", f"P11 Partial Repair {RUN_ID}"])],
    2,
)


def repair_metadata(user_env):
    return user_env[
        "odoo.ai.data.import.session"
    ].repair_metadata_for_current_user(partial_session)


repair_meta = fresh(importer_id, repair_metadata)
assert repair_meta["repair_revision"] == 1
assert repair_meta["last_repair_fingerprint"]

# Interruption semantics: a pre-commit loss rolls back both business rows and
# receipt; a committed chunk is then resumed from a fresh worker cursor.
set_import_cron(False)
try:
    interrupt_emails = [
        f"p11-interrupt-{RUN_ID}-{index}@example.test" for index in range(4)
    ]
    interrupt_turn, _attachment, interrupt_snapshot, interrupt_approvals, _seconds = (
        run_csv_turn(
            importer_id,
            filename="p11-interrupt.csv",
            csv_text="name,email\n"
            + "".join(
                f"P11 Interrupt {RUN_ID} {index},{email}\n"
                for index, email in enumerate(interrupt_emails)
            ),
            prompt=(
                "Importa este CSV en res.partner con assistant.data_import.inspect_csv y "
                "assistant.data_import.start_csv. Mapea columna 0 -> name y columna 1 -> "
                "email, usa chunk_size 2 y ejecuta el plan."
            ),
        )
    )
    assert "assistant.data_import.start_csv" in capability_names(interrupt_snapshot)
    interrupt_session = session_for_turn(importer_id, interrupt_turn)
    queued = session_snapshot(importer_id, interrupt_session)
    assert queued["state"] == "queued"
    assert queued["chunk_count"] == 0
    simulate_precommit_loss(interrupt_session)
    assert process_one_committed()
    after_first = session_snapshot(importer_id, interrupt_session)
    assert after_first["state"] == "queued"
    assert after_first["imported_rows"] == 2
    assert after_first["chunk_count"] == 1
    assert process_one_committed()
    after_restart = session_snapshot(importer_id, interrupt_session)
    assert after_restart["state"] == "completed"
    assert after_restart["imported_rows"] == 4
    assert after_restart["chunk_count"] == 2
    process_one_committed()
    replay = session_snapshot(importer_id, interrupt_session)
    assert replay["state"] == "completed"
    assert replay["imported_rows"] == 4
    assert replay["chunk_count"] == 2
    assert_partner_count(importer_id, [("email", "in", interrupt_emails)], 4)
finally:
    set_import_cron(True)

versions = environment_versions()
print(
    json.dumps(
        {
            "approvals": {
                "cleanup": clean_approvals,
                "interrupt": interrupt_approvals,
                "large": large_approvals,
                "partial": partial_approvals,
                "repair": repair_approvals,
                "small": small_approvals,
            },
            "effective_user_su_false": True,
            "event": "p11_real_import_gate_completed",
            "gates": {
                "P11-REAL-CSV-IMPORT": "PASS",
                "P11-REAL-IMPORT-RECEIPT": "PASS",
                "P11-REAL-LARGE-IMPORT": "PASS",
                "P11-REAL-MAPPING-CORRECTION": "PASS",
                "P11-REAL-PARTIAL-INVALID": "PASS",
                "P11-REAL-RESUME-NO-DUPLICATE": "PASS",
            },
            "metrics": {
                "cleanup": {
                    "corrected_rows": clean_status["corrected_rows"],
                    "fingerprint": cleanup_fingerprint,
                },
                "interruption": {
                    "actual_chunks": replay["chunk_count"],
                    "imported_rows": replay["imported_rows"],
                },
                "large": {
                    "actual_chunks": large_status["chunk_count"],
                    "chunk_size": large_status["chunk_size"],
                    "imported_rows": large_status["imported_rows"],
                    "planned_chunks": large_status["planned_chunk_count"],
                    "total_seconds": round(large_total_seconds, 3),
                    "turn_seconds": round(large_turn_seconds, 3),
                },
                "repair": {
                    "actual_chunks": repaired_status["chunk_count"],
                    "corrected_rows": repaired_status["corrected_rows"],
                    "fingerprint": repair_meta["last_repair_fingerprint"],
                    "repair_revision": repair_meta["repair_revision"],
                },
                "small": {
                    "actual_chunks": small_status["chunk_count"],
                    "imported_rows": small_status["imported_rows"],
                    "turn_seconds": round(small_turn_seconds, 3),
                },
                "partial_turn_seconds": round(partial_seconds, 3),
                "cleanup_turn_seconds": round(clean_turn_seconds, 3),
            },
            "run_id": RUN_ID,
            "tested_sha": TESTED_SHA,
            "versions": versions,
        },
        sort_keys=True,
    )
)
