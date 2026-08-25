"""Disposable M5 gate: Chromium -> Odoo 18 -> Assistant -> real Codex."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_m4_sale_order_codex import (
    GateError,
    _database_uri,
    _free_port,
    _json_request,
    _prefixed_json,
    _required_path,
    _run,
    _sanitized_log_tail,
    _start,
    _stop,
    _wait_url,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCRIPT = REPO_ROOT / "tests/e2e/m5_query_how_to_fixture.py"
BROWSER_SCRIPT = REPO_ROOT / "tests/e2e/m5_query_how_to_browser.mjs"
FIXTURE_ADDON = REPO_ROOT / "tests/fixtures/odoo18/odoo_ai_m5_guided_items"


def _browser(*, work: Path, playwright_root: Path, node: Path, env: dict[str, str], mode: str):
    script = work / f"m5-browser-{mode}.mjs"
    shutil.copy2(BROWSER_SCRIPT, script)
    modules = work / "node_modules"
    if not modules.exists():
        modules.symlink_to(playwright_root / "node_modules", target_is_directory=True)
    browser_env = dict(env)
    browser_env["M5_EXPECT_MODE"] = mode
    output = _run([str(node), str(script)], env=browser_env, cwd=work, timeout=900)
    return _prefixed_json(output, "M5_E2E_BROWSER=")


def _ingest_knowledge(service_env: dict[str, str], root: Path) -> dict[str, Any]:
    from odoo_ai.knowledge import (
        FilesystemKnowledgeProvider,
        KnowledgeIngestionService,
        KnowledgeSourceConfig,
        SqlAlchemyKnowledgeIngestStore,
    )
    from odoo_ai.storage import (
        DatabaseSettings,
        create_database_engine,
        create_session_factory,
        get_latest_instance_profile,
        session_scope,
    )

    engine = create_database_engine(DatabaseSettings.from_env(service_env))
    try:
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                raise GateError("source scan did not persist an instance profile")
            result = KnowledgeIngestionService(
                store=SqlAlchemyKnowledgeIngestStore(session)
            ).ingest(
                instance_profile_id=profile.id,
                provider=FilesystemKnowledgeProvider(
                    KnowledgeSourceConfig(
                        provider_id="m5.guidance",
                        root=root,
                        locale="es-ES",
                    )
                ),
            )
            return result.model_dump(mode="json")
    finally:
        engine.dispose()


def _tool_names(dsn: str, turn_id: str) -> list[str]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT attributes FROM trace_event "
            "WHERE trace_id = %s AND event_name = 'tool.completed' "
            "AND status = 'ok' ORDER BY sequence",
            (turn_id,),
        ).fetchall()
    return [
        name
        for (attributes,) in rows
        if isinstance(attributes, dict)
        and isinstance(name := attributes.get("tool_name"), str)
    ]


def _recent_trace(dsn: str) -> list[dict[str, object]]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT event_name, status, attributes FROM trace_event "
            "ORDER BY created_at DESC, sequence DESC LIMIT 24"
        ).fetchall()
    return [
        {"event": event, "status": status, "attributes": attributes}
        for event, status, attributes in reversed(rows)
    ]


def main() -> None:
    odoo_python = _required_path("M5_ODOO_PYTHON")
    odoo_bin = _required_path("M5_ODOO_BIN")
    core_addons = _required_path("M5_ODOO_CORE_ADDONS", directory=True)
    codex = _required_path("M5_CODEX_EXECUTABLE")
    playwright_root = _required_path("M5_PLAYWRIGHT_ROOT", directory=True)
    node = _required_path("M5_NODE")
    if not (playwright_root / "node_modules/playwright").is_dir():
        raise GateError("M5_PLAYWRIGHT_ROOT must contain node_modules/playwright")

    admin_dsn = os.environ.get("M5_POSTGRES_ADMIN_DSN", "").strip()
    parsed = urllib.parse.urlsplit(admin_dsn)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path.strip("/"):
        raise GateError("M5_POSTGRES_ADMIN_DSN must be a PostgreSQL URI")

    suffix = secrets.token_hex(5)
    odoo_role = f"m5_odoo_{suffix}"
    assistant_role = f"m5_assistant_{suffix}"
    odoo_db = f"m5_odoo_{suffix}"
    assistant_db = f"m5_assistant_{suffix}"
    odoo_password = secrets.token_urlsafe(24)
    assistant_password = secrets.token_urlsafe(24)
    processes = []
    logs = []
    created = False

    with tempfile.TemporaryDirectory(prefix="odoo-ai-m5-e2e-") as raw:
        work = Path(raw).resolve()
        fixture_addons = work / "fixture-addons"
        fixture_addons.mkdir()
        shutil.copytree(FIXTURE_ADDON, fixture_addons / FIXTURE_ADDON.name)
        knowledge_root = work / "knowledge"
        knowledge_root.mkdir()
        guide = knowledge_root / "guided-items.md"
        guide.write_text(
            "# Revisar elementos guiados\n\n"
            "Consulta la documentación configurada para saber cómo revisar los elementos "
            "guiados y localizar su código de guía en esta instalación. "
            "Abre el menú **M5 Guidance > Guided Items**. En la lista localiza "
            "la columna **Guide Code**, cuyo nombre técnico es `guide_code`. "
            "La lista respeta los permisos del usuario activo y es de solo lectura.\n",
            encoding="utf-8",
        )
        log_file = work / "m5-odoo.log"
        log_file.write_text("2026-08-23 10:00:00 INFO M5 readiness probe\n", encoding="utf-8")
        shared_secret = "m5-shared-" + secrets.token_urlsafe(48)
        delegation_secret = "m5-delegation-" + secrets.token_urlsafe(48)
        shared_file = work / "shared-secret"
        delegation_file = work / "delegation-secret"
        shared_file.write_text(shared_secret + "\n", encoding="utf-8")
        delegation_file.write_text(delegation_secret + "\n", encoding="utf-8")
        shared_file.chmod(0o600)
        delegation_file.chmod(0o600)
        pgpass = work / "pgpass"
        pgpass.write_text(
            f"{parsed.hostname}:{parsed.port or 5432}:*:{odoo_role}:{odoo_password}\n",
            encoding="utf-8",
        )
        pgpass.chmod(0o600)

        try:
            created = True
            with psycopg.connect(admin_dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(odoo_role), sql.Literal(odoo_password)))
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(assistant_role), sql.Literal(assistant_password)))
                # PostgreSQL 16 no longer implies SET ROLE merely from CREATEROLE.
                # The disposable cluster-admin needs explicit membership to assign
                # each new database to its deliberately separate least-privilege role.
                for role in (odoo_role, assistant_role):
                    connection.execute(
                        sql.SQL("GRANT {} TO CURRENT_USER").format(
                            sql.Identifier(role)
                        )
                    )
                for database, owner in ((odoo_db, odoo_role), (assistant_db, assistant_role)):
                    connection.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(database), sql.Identifier(owner)))
                    connection.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
                    connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(owner)))
            forbidden_dsn = _database_uri(parsed, assistant_role, assistant_password, odoo_db).replace("postgresql+psycopg://", "postgresql://")
            try:
                psycopg.connect(forbidden_dsn).close()
            except psycopg.OperationalError:
                pass
            else:
                raise GateError("Assistant role unexpectedly connected to Odoo DB")

            odoo_port = _free_port()
            assistant_port = _free_port()
            odoo_url = f"http://127.0.0.1:{odoo_port}"
            assistant_url = f"http://127.0.0.1:{assistant_port}"
            addons_path = ",".join((str(core_addons), str(REPO_ROOT / "addons"), str(fixture_addons)))
            common_env = dict(os.environ)
            common_env.update({
                "ODOO_AI_DELEGATION_SECRET_FILE": str(delegation_file),
                "ODOO_AI_SERVICE_URL": assistant_url,
                "ODOO_AI_SHARED_SECRET_FILE": str(shared_file),
                "ODOO_AI_TURN_TIMEOUT_SECONDS": "240",
                "PGPASSFILE": str(pgpass),
            })
            db_args = [
                f"--database={odoo_db}", f"--db_host={parsed.hostname}",
                f"--db_port={parsed.port or 5432}", f"--db_user={odoo_role}",
                f"--addons-path={addons_path}",
            ]
            _run([str(odoo_python), str(odoo_bin), *db_args, "--init=odoo_ai_assistant,odoo_ai_m5_guided_items", "--without-demo=all", "--stop-after-init"], env=common_env, timeout=360)

            fixture_env = dict(common_env)
            fixture_env.update({
                "M5_E2E_LOGIN_A": f"m5-user-a-{suffix}",
                "M5_E2E_LOGIN_B": f"m5-user-b-{suffix}",
                "M5_E2E_PASSWORD": secrets.token_urlsafe(18),
            })
            fixture_output = _run([str(odoo_python), str(odoo_bin), "shell", *db_args, "--no-http"], env=fixture_env, stdin=FIXTURE_SCRIPT, timeout=180)
            fixture = _prefixed_json(fixture_output, "M5_E2E_FIXTURE=")

            odoo_process, odoo_log = _start(
                [str(odoo_python), str(odoo_bin), *db_args, f"--http-port={odoo_port}", "--workers=0", "--max-cron-threads=0"],
                env=common_env, cwd=REPO_ROOT, log_path=work / "odoo-server.log",
            )
            processes.append(odoo_process)
            logs.append(odoo_log)
            _wait_url(f"{odoo_url}/web/login?db={odoo_db}")

            assistant_url_db = _database_uri(parsed, assistant_role, assistant_password, assistant_db)
            service_env = dict(common_env)
            service_env.update({
                "ODOO_AI_ALEMBIC_CONFIG": str(REPO_ROOT / "alembic.ini"),
                "ODOO_AI_CODEX_EXECUTABLE": str(codex),
                "ODOO_AI_CODEX_EXPERIMENTAL_API": "1",
                "ODOO_AI_CODEX_MODEL": os.environ.get("M5_CODEX_MODEL", "gpt-5.4"),
                "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS": "220",
                "ODOO_AI_DATABASE_NAME": assistant_db,
                "ODOO_AI_DATABASE_URL": assistant_url_db,
                "ODOO_AI_KNOWLEDGE_SOURCES": json.dumps([{"provider_id": "m5.guidance", "root": str(knowledge_root), "locale": "es-ES"}]),
                "ODOO_AI_LOG_FILE": str(log_file),
                "ODOO_AI_ODOO_BASE_URL": odoo_url,
                "ODOO_AI_PORT": str(assistant_port),
                "ODOO_AI_SOURCE_ROOTS": json.dumps([str(fixture_addons), str(REPO_ROOT / "addons")]),
            })
            _run([str(REPO_ROOT / ".venv/bin/python"), "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), "upgrade", "head"], env=service_env, timeout=180)
            service_process, service_log = _start([str(REPO_ROOT / ".venv/bin/python"), "-m", "odoo_ai.api"], env=service_env, cwd=REPO_ROOT / "service", log_path=work / "assistant-service.log")
            processes.append(service_process)
            logs.append(service_log)
            _wait_url(f"{assistant_url}/health")
            source = _json_request(f"{assistant_url}/v1/admin/source/rescan", secret=shared_secret, payload={})
            if source.get("state") != "DETECTED":
                raise GateError("source scan did not become operational")
            first_ingest = _ingest_knowledge(service_env, knowledge_root)
            _json_request(f"{assistant_url}/v1/admin/logs/test", secret=shared_secret, payload={"terms": ["M5"], "max_lines": 20, "max_bytes": 8192})
            ready = _json_request(f"{assistant_url}/v1/admin/status", secret=shared_secret)
            if ready.get("readiness") != "FULLY_READY":
                raise GateError("FULLY_READY was not demonstrated")

            browser_env = dict(fixture_env)
            browser_env.update({
                "M5_ACTION_ID": str(fixture["action_id"]),
                "M5_ASSISTANT_BASE_URL": assistant_url,
                "M5_FORBIDDEN_VALUES": ",".join((shared_secret, delegation_secret, assistant_password, odoo_password, str(fixture_addons), str(knowledge_root))),
                "M5_HIDDEN_NAME": fixture["hidden_name"],
                "M5_MENU_ID": str(fixture["menu_id"]),
                "M5_MODEL": fixture["model"],
                "M5_ODOO_BASE_URL": odoo_url,
                "M5_ODOO_DATABASE": odoo_db,
            })
            try:
                positive = _browser(
                    work=work,
                    playwright_root=playwright_root,
                    node=node,
                    env=browser_env,
                    mode="positive",
                )
            except GateError as error:
                service_log.flush()
                odoo_log.flush()
                forbidden = (
                    shared_secret,
                    delegation_secret,
                    assistant_password,
                    odoo_password,
                    str(fixture_addons),
                    str(knowledge_root),
                )
                raise GateError(
                    f"{error}\nassistant log:\n"
                    f"{_sanitized_log_tail(work / 'assistant-service.log', forbidden)}\n"
                    f"recent trace:\n"
                    f"{json.dumps(_recent_trace(assistant_url_db.replace('postgresql+psycopg://', 'postgresql://')), ensure_ascii=False)}\n"
                    f"odoo log:\n"
                    f"{_sanitized_log_tail(work / 'odoo-server.log', forbidden)}"
                ) from None
            assistant_dsn = assistant_url_db.replace("postgresql+psycopg://", "postgresql://")
            query_tools = _tool_names(assistant_dsn, positive["query_a"]["turn_id"])
            how_to_tools = _tool_names(assistant_dsn, positive["how_to"]["turn_id"])
            if "odoo.aggregate_records" not in query_tools:
                raise GateError("real QUERY did not use bounded aggregate_records")
            if not {"knowledge.search", "knowledge.read_excerpt"}.issubset(how_to_tools):
                raise GateError("real HOW_TO did not use the required knowledge tools")

            old_document = next(c for c in positive["how_to"]["citations"] if c["kind"] == "document")
            guide.unlink()
            retired = _ingest_knowledge(service_env, knowledge_root)
            stale = _browser(work=work, playwright_root=playwright_root, node=node, env=browser_env, mode="stale")
            if old_document["fingerprint"] in json.dumps(stale, ensure_ascii=False):
                raise GateError("retired knowledge fingerprint was reused")

            _stop(service_process)
            service_env["ODOO_AI_CODEX_EXECUTABLE"] = str(work / "missing-codex")
            degraded_process, degraded_log = _start([str(REPO_ROOT / ".venv/bin/python"), "-m", "odoo_ai.api"], env=service_env, cwd=REPO_ROOT / "service", log_path=work / "assistant-degraded.log")
            processes.append(degraded_process)
            logs.append(degraded_log)
            _wait_url(f"{assistant_url}/health")
            degraded = _json_request(f"{assistant_url}/v1/admin/status", secret=shared_secret)
            if degraded.get("readiness") != "DEGRADED" or degraded.get("components", {}).get("reasoning_engine", {}).get("detail") != "runtime_missing":
                raise GateError("missing Codex did not produce actionable DEGRADED status")
            unavailable = _browser(work=work, playwright_root=playwright_root, node=node, env=browser_env, mode="engine_unavailable")

            serialized = json.dumps((positive, stale, unavailable), ensure_ascii=False)
            for forbidden in (shared_secret, delegation_secret, assistant_password, odoo_password, str(fixture_addons), str(knowledge_root), fixture["hidden_name"]):
                if forbidden in serialized:
                    raise GateError("secret, physical path, or ACL-hidden record leaked")
            print("M5_E2E_RESULT=" + json.dumps({
                "full_readiness": ready["readiness"],
                "how_to_citation_kinds": sorted({c["kind"] for c in positive["how_to"]["citations"]}),
                "how_to_tools": how_to_tools,
                "knowledge_ingest": first_ingest["metrics"],
                "knowledge_retirement": retired["metrics"],
                "missing_codex_readiness": degraded["readiness"],
                "query_a_answer": positive["query_a"]["answer"],
                "query_b_answer": positive["query_b"]["answer"],
                "query_tools": query_tools,
                "rejected_error": positive["rejected"]["error"]["code"],
                "stale_result": "bounded_answer" if stale["how_to"].get("ok") else stale["how_to"]["error"]["code"],
                "unavailable_error": unavailable["query_a"]["error"]["code"],
            }, ensure_ascii=False, sort_keys=True))
        finally:
            for process in reversed(processes):
                _stop(process)
            for log in logs:
                log.close()
            if created:
                with psycopg.connect(admin_dsn, autocommit=True) as connection:
                    for database in (odoo_db, assistant_db):
                        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
                    for role in (odoo_role, assistant_role):
                        connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"M5_E2E_ERROR={error}", file=sys.stderr)
        raise SystemExit(1) from None
