"""Focused real Odoo/Codex acceptance gates for Phase-9 company Knowledge.

Run through ``odoo-bin shell`` against a disposable database while an independent
Odoo process serves cron workers. Output is sanitized gate state only.
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from odoo import Command, api
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import CapabilityContext
from odoo.addons.odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProviderCatalog,
    EvidenceSearchRequest,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.knowledge_evidence import (
    build_company_knowledge_evidence_provider,
)
from odoo.modules.registry import Registry

env = globals()["env"]
DBNAME = env.cr.dbname
if not DBNAME.startswith("odoo_ai_"):
    raise RuntimeError("P9 real gates require a disposable odoo_ai_* database")

CODEX_EXECUTABLE = os.environ.get("P9_CODEX_EXECUTABLE", "").strip()
if not CODEX_EXECUTABLE:
    raise RuntimeError("P9_CODEX_EXECUTABLE is required")

ADMIN_ID = env.ref("base.user_admin").id
COMPANY_ID = env.company.id
TERMINAL = {"completed", "failed", "cancelled", "recovery_required"}


def fresh(uid: int, callback: Callable):
    with Registry(DBNAME).cursor() as cr:
        user_env = api.Environment(
            cr,
            uid,
            {"allowed_company_ids": [COMPANY_ID], "lang": "en_US"},
            su=False,
        )
        assert not user_env.su
        result = callback(user_env)
        cr.commit()
        user_env.registry.signal_changes()
        return result


def configure() -> None:
    fresh(
        ADMIN_ID,
        lambda admin_env: admin_env["ir.config_parameter"].set_param(
            "odoo_ai_assistant.codex_executable", CODEX_EXECUTABLE
        ),
    )


def screen() -> dict[str, object]:
    return {
        "action_id": None,
        "allowed_context_subset": {},
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "menu_id": None,
        "model": None,
        "res_id": None,
        "selected_ids": [],
        "view_type": "list",
    }


def snapshot(user_env, turn_uuid: str) -> dict[str, object]:
    turn = user_env["odoo.ai.turn"]._owned_turn(turn_uuid)
    answer = turn.assistant_message_id.content if turn.assistant_message_id else ""
    response = dict(turn.result_payload or {})
    return {
        "state": turn.state,
        "answer": answer or "",
        "citations": list(response.get("citations") or []),
        "error_code": turn.error_code or "",
    }


def wait_turn(turn_uuid: str, *, uid=ADMIN_ID) -> dict[str, object]:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        value = fresh(uid, lambda user_env: snapshot(user_env, turn_uuid))
        if value["state"] in TERMINAL | {"awaiting_confirmation"}:
            if value["state"] == "awaiting_confirmation":
                raise AssertionError("unexpected_approval_boundary")
            return value
        time.sleep(0.5)
    raise AssertionError("p9_real_turn_timeout")


def run_turn(message: str) -> dict[str, object]:
    turn_uuid = fresh(
        ADMIN_ID,
        lambda user_env: user_env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=screen(),
            conversation_uuid=None,
            client_request_id=f"p9.real.{uuid.uuid4().hex}",
            planning_mode="adaptive",
        )["turn_id"],
    )
    return wait_turn(turn_uuid)


def assert_completed(value: dict[str, object]) -> str:
    assert value["state"] == "completed", value["error_code"]
    answer = str(value["answer"])
    lowered = answer.casefold()
    assert not any(
        token in lowered
        for token in ("access_token", "raw_reasoning", "refresh_token", "stderr")
    )
    return lowered


def encode(text: str) -> bytes:
    return base64.b64encode(text.encode("utf-8"))


def create_and_index_source(
    *,
    name: str,
    text: str,
    access_mode="company",
    uid=ADMIN_ID,
) -> tuple[int, str]:
    def create(user_env):
        source = user_env["odoo.ai.knowledge.source"].create(
            {
                "name": name,
                "filename": f"{name}.txt",
                "mimetype": "text/plain",
                "data": encode(text),
                "access_mode": access_mode,
            }
        )
        assert source.state == "uploaded"
        source.action_process_now()
        assert source.state == "active"
        assert source.chunk_count > 0
        return source.id, source.source_uuid

    return fresh(uid, create)


def upload_ingest_gate() -> tuple[int, str]:
    source_id, source_uuid = create_and_index_source(
        name=f"p9-upload-{uuid.uuid4().hex[:8]}",
        text="P9_UPLOAD_INGEST_MARKER handbook upload accepted and indexed.",
    )
    assert len(source_uuid) == 32
    return source_id, source_uuid


def lexical_citation_gate() -> tuple[int, object]:
    source_id, _source_uuid = create_and_index_source(
        name=f"p9-policy-{uuid.uuid4().hex[:8]}",
        text=(
            "P9_POLICY_MARKER_6402. Internal company policy: critical customer "
            "incidents must be escalated to the duty manager."
        ),
    )
    result = run_turn(
        "Según la política interna de la empresa, ¿a quién se escalan los incidentes "
        "críticos de clientes? Incluye la evidencia/cita usada y el marcador exacto."
    )
    answer = assert_completed(result)
    assert "duty manager" in answer
    assert "p9_policy_marker_6402" in answer
    citations = [item for item in result["citations"] if isinstance(item, dict)]
    knowledge = [
        item
        for item in citations
        if item.get("kind") == "document"
        and isinstance(item.get("citation"), dict)
        and item["citation"].get("source_type") == "company_knowledge"
    ]
    assert knowledge
    return source_id, knowledge[0]


def acl_gate() -> None:
    suffix = uuid.uuid4().hex[:10]

    def create_user(admin_env):
        group = admin_env.ref("base.group_user")
        user = admin_env["res.users"].create(
            {
                "name": f"P9 ACL User {suffix}",
                "login": f"p9-acl-{suffix}",
                "company_id": COMPANY_ID,
                "company_ids": [Command.set([COMPANY_ID])],
                "groups_id": [Command.set([group.id])],
            }
        )
        return user.id

    user_id = fresh(ADMIN_ID, create_user)
    company_id, _ = create_and_index_source(
        name=f"p9-company-{suffix}",
        text="P9_COMPANY_VISIBLE_MARKER",
        access_mode="company",
    )
    private_id, _ = create_and_index_source(
        name=f"p9-private-{suffix}",
        text="P9_PRIVATE_HIDDEN_MARKER",
        access_mode="private",
    )

    def inspect(user_env):
        sources = user_env["odoo.ai.knowledge.source"]
        assert sources.browse(company_id).exists()
        assert not sources.search([("id", "=", private_id)])
        assert sources.lexical_search("P9_COMPANY_VISIBLE_MARKER")
        assert not sources.lexical_search("P9_PRIVATE_HIDDEN_MARKER")

    fresh(user_id, inspect)


def reindex_gate(source_id: int) -> None:
    def run(admin_env):
        source = admin_env["odoo.ai.knowledge.source"].browse(source_id).exists()
        context = CapabilityContext(env=admin_env, turn_id="p9-real-reindex")
        catalog = EvidenceProviderCatalog((build_company_knowledge_evidence_provider(),))
        batch = catalog.search(
            context,
            EvidenceSearchRequest(
                query="P9_POLICY_MARKER_6402 duty manager",
                kinds=(EvidenceKind.DOCUMENT,),
            ),
        )
        ref = next(item for item in batch.refs if item.citation["source_uuid"] == source.source_uuid)
        source.write(
            {
                "data": encode(
                    "P9_POLICY_MARKER_7713. Revised internal policy: critical customer "
                    "incidents must be escalated to the incident lead."
                )
            }
        )
        assert source.state == "uploaded"
        stale = catalog.fetch(context, ref)
        assert stale.ref.freshness is EvidenceFreshness.STALE
        source.action_process_now()
        assert source.version >= 2
        stale = catalog.fetch(context, ref)
        assert stale.ref.freshness is EvidenceFreshness.STALE
        newer = catalog.search(
            context,
            EvidenceSearchRequest(
                query="P9_POLICY_MARKER_7713 incident lead",
                kinds=(EvidenceKind.DOCUMENT,),
            ),
        )
        assert any(
            item.citation["source_uuid"] == source.source_uuid for item in newer.refs
        )

    fresh(ADMIN_ID, run)


def chat_ingest_gate() -> None:
    request_id = f"p9.real.chat.{uuid.uuid4().hex}"

    def enqueue(user_env):
        attachment = user_env["odoo.ai.knowledge.attachment"].create_upload(
            filename="p9-chat-knowledge.txt",
            mimetype="text/plain",
            data=encode(
                "P9_CHAT_INGEST_MARKER_9304. Chat-uploaded company Knowledge source."
            ),
        )
        result = user_env["odoo.ai.turn"].enqueue_for_current_user(
            message=(
                "Añade explícitamente este archivo a Knowledge de la empresa y confirma "
                "cuando la fuente haya quedado creada."
                f"\n[[odoo_ai_attachment:{attachment.token}]]"
            ),
            screen=screen(),
            conversation_uuid=None,
            client_request_id=request_id,
            planning_mode="adaptive",
        )
        return result["turn_id"], attachment.id

    turn_uuid, attachment_id = fresh(ADMIN_ID, enqueue)
    result = wait_turn(turn_uuid)
    assert_completed(result)

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = fresh(
            ADMIN_ID,
            lambda user_env: _attachment_source_state(user_env, attachment_id),
        )
        if state == "active":
            return
        if state == "error":
            raise AssertionError("chat_knowledge_source_index_error")
        time.sleep(0.5)
    raise AssertionError("chat_knowledge_source_not_active")


def _attachment_source_state(user_env, attachment_id: int) -> str:
    attachment = user_env["odoo.ai.knowledge.attachment"].browse(attachment_id).exists()
    assert attachment and attachment.turn_id
    assert attachment.turn_id.user_message_id.content.startswith("Añade explícitamente")
    assert "odoo_ai_attachment" not in attachment.turn_id.user_message_id.content
    source = attachment.knowledge_source_id
    assert source, "assistant.knowledge.ingest_attachment was not executed"
    return source.state


def large_document_gate() -> None:
    marker = "P9_LARGE_DOCUMENT_MARKER_5571"
    paragraphs = [
        f"{marker} paragraph {index}: bounded deterministic ingestion content."
        for index in range(12_000)
    ]
    text = "\n\n".join(paragraphs)
    assert len(text.encode("utf-8")) < 8 * 1024 * 1024

    def run(admin_env):
        started = time.monotonic()
        source = admin_env["odoo.ai.knowledge.source"].create(
            {
                "name": "p9-large-document",
                "filename": "p9-large-document.txt",
                "mimetype": "text/plain",
                "data": encode(text),
                "access_mode": "company",
            }
        )
        source.action_process_now()
        elapsed = time.monotonic() - started
        assert source.state == "active"
        assert 1 <= source.chunk_count <= 2_048
        assert admin_env["odoo.ai.knowledge.source"].lexical_search(marker, limit=4)
        assert elapsed < 30, elapsed

    fresh(ADMIN_ID, run)


configure()
upload_ingest_gate()
policy_source_id, _citation = lexical_citation_gate()
acl_gate()
reindex_gate(policy_source_id)
chat_ingest_gate()
large_document_gate()

print(
    json.dumps(
        {
            "effective_user_su_false": True,
            "event": "p9_real_knowledge_gate_completed",
            "gates": {
                "P9-REAL-ACL": "PASS",
                "P9-REAL-CHAT-INGEST": "PASS",
                "P9-REAL-CITATIONS": "PASS",
                "P9-REAL-FTS": "PASS",
                "P9-REAL-LARGE-DOCUMENT": "PASS",
                "P9-REAL-REINDEX": "PASS",
                "P9-REAL-UPLOAD-INGEST": "PASS",
            },
            "semantic_gain_gate": "NOT_APPLICABLE_NO_VECTOR_BACKEND",
        },
        sort_keys=True,
    )
)
