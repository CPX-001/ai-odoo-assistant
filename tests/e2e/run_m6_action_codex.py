"""Disposable M6 gate: Chromium -> Odoo 18 -> Assistant -> real Codex ACTION."""

from __future__ import annotations

import http.client
import json
import os
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_m4_sale_order_codex import (  # noqa: E402
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
FIXTURE_SCRIPT = REPO_ROOT / "tests/e2e/m6_action_fixture.py"
BROWSER_SCRIPT = REPO_ROOT / "tests/e2e/m6_action_browser.mjs"
FIXTURE_ADDON = REPO_ROOT / "tests/fixtures/odoo18/odoo_ai_m6_action_items"


class _DropCommitProxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], upstream_port: int, record_id: int):
        super().__init__(address, _ProxyHandler)
        self.upstream_port = upstream_port
        self.record_id = record_id
        self.drop_count = 0
        self._lock = threading.Lock()

    def should_drop(self, path: str, body: bytes) -> bool:
        if path != "/odoo_ai/internal/v1/action-commit":
            return False
        try:
            payload = json.loads(body)
            record_id = payload["proposal"]["target"]["record_id"]
        except (KeyError, TypeError, ValueError):
            return False
        with self._lock:
            if record_id != self.record_id or self.drop_count:
                return False
            self.drop_count += 1
            return True


class _ProxyHandler(BaseHTTPRequestHandler):
    server: _DropCommitProxy

    def do_GET(self) -> None:  # noqa: N802
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _forward(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.upstream_port, timeout=240
            )
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.casefold() not in {"connection", "content-length", "host"}
            }
            headers["Host"] = f"127.0.0.1:{self.server.upstream_port}"
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = response.read()
            response_headers = response.getheaders()
            connection.close()
            if self.server.should_drop(self.path, body):
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(response.status)
            for key, value in response_headers:
                if key.casefold() not in {
                    "connection",
                    "content-length",
                    "transfer-encoding",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except (ConnectionError, OSError, ValueError):
            self.close_connection = True


def _browser(
    *,
    work: Path,
    playwright_root: Path,
    node: Path,
    env: dict[str, str],
    mode: str,
) -> dict[str, Any]:
    script = work / f"m6-browser-{mode}.mjs"
    shutil.copy2(BROWSER_SCRIPT, script)
    modules = work / "node_modules"
    if not modules.exists():
        modules.symlink_to(playwright_root / "node_modules", target_is_directory=True)
    browser_env = dict(env)
    browser_env["M6_EXPECT_MODE"] = mode
    output = _run([str(node), str(script)], env=browser_env, cwd=work, timeout=1_200)
    return _prefixed_json(output, "M6_E2E_BROWSER=")


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


def _action_evidence(dsn: str) -> dict[str, Any]:
    with psycopg.connect(dsn) as connection:
        proposals = connection.execute(
            "SELECT proposal_id, turn_id, state, approval_id, attempt_id, evidence_id, "
            "payload_fingerprint, error_code FROM action_proposal ORDER BY created_at"
        ).fetchall()
        audits = connection.execute(
            "SELECT proposal_id, attempt_id, event_type, state, actor_uid, "
            "payload_fingerprint, error_code FROM action_audit_event ORDER BY created_at"
        ).fetchall()
    return {
        "audits": [
            {
                "actor_uid": actor_uid,
                "attempt_id": str(attempt_id) if attempt_id else None,
                "error_code": error_code,
                "event_type": event_type,
                "payload_fingerprint": fingerprint,
                "proposal_id": str(proposal_id),
                "state": state,
            }
            for proposal_id, attempt_id, event_type, state, actor_uid, fingerprint, error_code in audits
        ],
        "proposals": [
            {
                "approval_id": str(approval_id) if approval_id else None,
                "attempt_id": str(attempt_id) if attempt_id else None,
                "error_code": error_code,
                "evidence_id": str(evidence_id) if evidence_id else None,
                "payload_fingerprint": fingerprint,
                "proposal_id": str(proposal_id),
                "state": state,
                "turn_id": str(turn_id),
            }
            for proposal_id, turn_id, state, approval_id, attempt_id, evidence_id, fingerprint, error_code in proposals
        ],
    }


def _expire(dsn: str, proposal_id: str) -> None:
    with psycopg.connect(dsn) as connection:
        result = connection.execute(
            "UPDATE action_proposal SET expires_at = clock_timestamp() - interval '1 second' "
            "WHERE proposal_id = %s AND state = 'previewed'",
            (proposal_id,),
        )
        if result.rowcount != 1:
            raise GateError("expiry fixture proposal was not previewed")
        connection.commit()


def _recent_trace(dsn: str) -> list[dict[str, object]]:
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT event_name, status, attributes FROM trace_event "
            "ORDER BY created_at DESC, sequence DESC LIMIT 32"
        ).fetchall()
    return [
        {"attributes": attributes, "event": event, "status": status}
        for event, status, attributes in reversed(rows)
    ]


def main() -> None:
    odoo_python = _required_path("M6_ODOO_PYTHON")
    odoo_bin = _required_path("M6_ODOO_BIN")
    core_addons = _required_path("M6_ODOO_CORE_ADDONS", directory=True)
    codex = _required_path("M6_CODEX_EXECUTABLE")
    playwright_root = _required_path("M6_PLAYWRIGHT_ROOT", directory=True)
    node = _required_path("M6_NODE")
    if not (playwright_root / "node_modules/playwright").is_dir():
        raise GateError("M6_PLAYWRIGHT_ROOT must contain node_modules/playwright")

    admin_dsn = os.environ.get("M6_POSTGRES_ADMIN_DSN", "").strip()
    parsed = urllib.parse.urlsplit(admin_dsn)
    if (
        parsed.scheme not in {"postgresql", "postgres"}
        or not parsed.hostname
        or not parsed.path.strip("/")
    ):
        raise GateError("M6_POSTGRES_ADMIN_DSN must be a PostgreSQL URI")

    suffix = secrets.token_hex(5)
    odoo_role = f"m6_odoo_{suffix}"
    assistant_role = f"m6_assistant_{suffix}"
    odoo_db = f"m6_odoo_{suffix}"
    assistant_db = f"m6_assistant_{suffix}"
    odoo_password = secrets.token_urlsafe(24)
    assistant_password = secrets.token_urlsafe(24)
    processes: list[Any] = []
    logs: list[Any] = []
    proxy: _DropCommitProxy | None = None
    proxy_thread: threading.Thread | None = None
    created = False

    with tempfile.TemporaryDirectory(prefix="odoo-ai-m6-e2e-") as raw:
        work = Path(raw).resolve()
        fixture_addons = work / "fixture-addons"
        fixture_addons.mkdir()
        shutil.copytree(FIXTURE_ADDON, fixture_addons / FIXTURE_ADDON.name)
        log_file = work / "m6-odoo.log"
        log_file.write_text("2026-08-23 10:00:00 INFO M6 readiness probe\n", encoding="utf-8")
        shared_secret = "m6-shared-" + secrets.token_urlsafe(48)
        delegation_secret = "m6-delegation-" + secrets.token_urlsafe(48)
        authority_secret = "m6-authority-" + secrets.token_urlsafe(48)
        secret_values = (shared_secret, delegation_secret, authority_secret, assistant_password, odoo_password)
        shared_file = work / "shared-secret"
        delegation_file = work / "delegation-secret"
        authority_file = work / "action-authority-secret"
        for path, value in (
            (shared_file, shared_secret),
            (delegation_file, delegation_secret),
            (authority_file, authority_secret),
        ):
            path.write_text(value + "\n", encoding="utf-8")
            path.chmod(0o600)
        pgpass = work / "pgpass"
        pgpass.write_text(
            f"{parsed.hostname}:{parsed.port or 5432}:*:{odoo_role}:{odoo_password}\n",
            encoding="utf-8",
        )
        pgpass.chmod(0o600)

        try:
            created = True
            with psycopg.connect(admin_dsn, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(odoo_role), sql.Literal(odoo_password)
                    )
                )
                connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(assistant_role), sql.Literal(assistant_password)
                    )
                )
                for role in (odoo_role, assistant_role):
                    connection.execute(
                        sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(role))
                    )
                for database_name, owner in (
                    (odoo_db, odoo_role),
                    (assistant_db, assistant_role),
                ):
                    connection.execute(
                        sql.SQL(
                            "CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0"
                        ).format(sql.Identifier(database_name), sql.Identifier(owner))
                    )
                    connection.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                            sql.Identifier(database_name)
                        )
                    )
                    connection.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(database_name), sql.Identifier(owner)
                        )
                    )
            forbidden_dsn = _database_uri(
                parsed, assistant_role, assistant_password, odoo_db
            ).replace("postgresql+psycopg://", "postgresql://")
            try:
                psycopg.connect(forbidden_dsn).close()
            except psycopg.OperationalError:
                pass
            else:
                raise GateError("Assistant role unexpectedly connected to Odoo DB")

            odoo_port = _free_port()
            proxy_port = _free_port()
            assistant_port = _free_port()
            odoo_url = f"http://127.0.0.1:{odoo_port}"
            proxy_url = f"http://127.0.0.1:{proxy_port}"
            assistant_url = f"http://127.0.0.1:{assistant_port}"
            addons_path = ",".join(
                (str(core_addons), str(REPO_ROOT / "addons"), str(fixture_addons))
            )
            common_env = dict(os.environ)
            common_env.update(
                {
                    "ODOO_AI_ACTION_AUTHORITY_SECRET_FILE": str(authority_file),
                    "ODOO_AI_DELEGATION_SECRET_FILE": str(delegation_file),
                    "ODOO_AI_SERVICE_URL": assistant_url,
                    "ODOO_AI_SHARED_SECRET_FILE": str(shared_file),
                    "ODOO_AI_TURN_TIMEOUT_SECONDS": "240",
                    "PGPASSFILE": str(pgpass),
                }
            )
            db_args = [
                f"--database={odoo_db}",
                f"--db_host={parsed.hostname}",
                f"--db_port={parsed.port or 5432}",
                f"--db_user={odoo_role}",
                f"--addons-path={addons_path}",
            ]
            _run(
                [
                    str(odoo_python),
                    str(odoo_bin),
                    *db_args,
                    "--init=odoo_ai_assistant,odoo_ai_m6_action_items",
                    "--without-demo=all",
                    "--stop-after-init",
                ],
                env=common_env,
                timeout=360,
            )
            _run(
                [
                    str(odoo_python),
                    str(odoo_bin),
                    *db_args,
                    "--update=odoo_ai_assistant,odoo_ai_m6_action_items",
                    "--without-demo=all",
                    "--stop-after-init",
                ],
                env=common_env,
                timeout=360,
            )
            fixture_env = dict(common_env)
            fixture_env.update(
                {
                    "M6_E2E_LOGIN_A": f"m6-user-a-{suffix}",
                    "M6_E2E_LOGIN_B": f"m6-user-b-{suffix}",
                    "M6_E2E_PASSWORD": secrets.token_urlsafe(18),
                }
            )
            fixture_output = _run(
                [str(odoo_python), str(odoo_bin), "shell", *db_args, "--no-http"],
                env=fixture_env,
                stdin=FIXTURE_SCRIPT,
                timeout=180,
            )
            fixture = _prefixed_json(fixture_output, "M6_E2E_FIXTURE=")

            odoo_process, odoo_log = _start(
                [
                    str(odoo_python),
                    str(odoo_bin),
                    *db_args,
                    f"--http-port={odoo_port}",
                    "--workers=0",
                    "--max-cron-threads=0",
                ],
                env=common_env,
                cwd=REPO_ROOT,
                log_path=work / "odoo-server.log",
            )
            processes.append(odoo_process)
            logs.append(odoo_log)
            _wait_url(f"{odoo_url}/web/login?db={odoo_db}")

            proxy = _DropCommitProxy(
                ("127.0.0.1", proxy_port),
                odoo_port,
                int(fixture["items"]["ambiguous"]),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            assistant_url_db = _database_uri(
                parsed, assistant_role, assistant_password, assistant_db
            )
            assistant_dsn = assistant_url_db.replace(
                "postgresql+psycopg://", "postgresql://"
            )
            service_env = dict(common_env)
            service_env.update(
                {
                    "ODOO_AI_ALEMBIC_CONFIG": str(REPO_ROOT / "alembic.ini"),
                    "ODOO_AI_CODEX_EXECUTABLE": str(codex),
                    "ODOO_AI_CODEX_EXPERIMENTAL_API": "1",
                    "ODOO_AI_CODEX_MODEL": os.environ.get("M6_CODEX_MODEL", "gpt-5.4"),
                    "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS": "220",
                    "ODOO_AI_DATABASE_NAME": assistant_db,
                    "ODOO_AI_DATABASE_URL": assistant_url_db,
                    "ODOO_AI_LOG_FILE": str(log_file),
                    "ODOO_AI_ODOO_BASE_URL": proxy_url,
                    "ODOO_AI_PORT": str(assistant_port),
                    "ODOO_AI_SOURCE_ROOTS": json.dumps(
                        [str(fixture_addons), str(REPO_ROOT / "addons")]
                    ),
                }
            )
            _run(
                [
                    str(REPO_ROOT / ".venv/bin/python"),
                    "-m",
                    "alembic",
                    "-c",
                    str(REPO_ROOT / "alembic.ini"),
                    "upgrade",
                    "head",
                ],
                env=service_env,
                timeout=180,
            )
            service_process, service_log = _start(
                [str(REPO_ROOT / ".venv/bin/python"), "-m", "odoo_ai.api"],
                env=service_env,
                cwd=REPO_ROOT / "service",
                log_path=work / "assistant-service.log",
            )
            processes.append(service_process)
            logs.append(service_log)
            _wait_url(f"{assistant_url}/health")
            source = _json_request(
                f"{assistant_url}/v1/admin/source/rescan",
                secret=shared_secret,
                payload={},
            )
            if source.get("state") != "DETECTED":
                raise GateError("source scan did not become operational")
            _json_request(
                f"{assistant_url}/v1/admin/logs/test",
                secret=shared_secret,
                payload={"max_bytes": 8192, "max_lines": 20, "terms": ["M6"]},
            )
            ready = _json_request(
                f"{assistant_url}/v1/admin/status", secret=shared_secret
            )
            if (
                ready.get("readiness") != "FULLY_READY"
                or ready.get("workflow_capabilities", {})
                .get("action", {})
                .get("state")
                != "ok"
            ):
                raise GateError("FULLY_READY ACTION capability was not demonstrated")

            browser_env = dict(fixture_env)
            browser_env.update(
                {
                    "M6_ACTION_ID": str(fixture["action_id"]),
                    "M6_ASSISTANT_BASE_URL": assistant_url,
                    "M6_FORBIDDEN_VALUES": ",".join(
                        (*secret_values, str(fixture_addons))
                    ),
                    "M6_ITEMS": json.dumps(fixture["items"], sort_keys=True),
                    "M6_MENU_ID": str(fixture["menu_id"]),
                    "M6_MODEL": fixture["model"],
                    "M6_ODOO_BASE_URL": odoo_url,
                    "M6_ODOO_DATABASE": odoo_db,
                }
            )
            try:
                positive = _browser(
                    work=work,
                    playwright_root=playwright_root,
                    node=node,
                    env=browser_env,
                    mode="main",
                )
            except GateError as error:
                service_log.flush()
                odoo_log.flush()
                raise GateError(
                    f"{error}\nassistant log:\n"
                    f"{_sanitized_log_tail(work / 'assistant-service.log', secret_values)}\n"
                    f"recent trace:\n"
                    f"{json.dumps(_recent_trace(assistant_dsn), ensure_ascii=False)}\n"
                    f"odoo log:\n"
                    f"{_sanitized_log_tail(work / 'odoo-server.log', secret_values)}"
                ) from None

            if proxy.drop_count != 1:
                raise GateError("ambiguous commit response was not dropped exactly once")
            preview_tools = {
                "odoo.get_effective_write_schema",
                "odoo.preview_record_patch",
            }
            turn_tools: dict[str, list[str]] = {}
            for key in ("happy", "ambiguous", "expiry"):
                tools = _tool_names(assistant_dsn, positive[key]["turn_id"])
                if set(tools) != preview_tools or len(tools) != 2:
                    raise GateError(f"ACTION {key} registry/tools were not exact: {tools}")
                if any("commit" in name or "approve" in name for name in tools):
                    raise GateError("Codex received an approval or commit tool")
                turn_tools[key] = tools

            expiry_proposal = positive["expiry"]["proposal"]["proposal_id"]
            _expire(assistant_dsn, expiry_proposal)
            expiry_env = dict(browser_env)
            expiry_env["M6_EXPIRY_PROPOSAL_ID"] = expiry_proposal
            expired = _browser(
                work=work,
                playwright_root=playwright_root,
                node=node,
                env=expiry_env,
                mode="expiry",
            )
            evidence = _action_evidence(assistant_dsn)
            states = {item["state"] for item in evidence["proposals"]}
            if not {"verified", "rejected", "stale", "previewed"}.issubset(states):
                raise GateError(f"required durable ACTION states missing: {sorted(states)}")
            serialized = json.dumps((positive, expired, evidence), ensure_ascii=False)
            for forbidden in (*secret_values, str(fixture_addons), "FORBIDDEN M6 COMPANY-B RECORD"):
                if forbidden in serialized:
                    raise GateError("secret, path, or ACL-hidden record leaked")

            odoo_version = _run([str(odoo_python), str(odoo_bin), "--version"], timeout=60).strip()
            codex_version = _run([str(codex), "--version"], timeout=60).strip()
            print(
                "M6_E2E_RESULT="
                + json.dumps(
                    {
                        "ambiguous_response_drops": proxy.drop_count,
                        "audit_events": len(evidence["audits"]),
                        "browser_to_assistant_requests": 0,
                        "codex_version": codex_version,
                        "correlations": evidence["proposals"],
                        "expiry_error": expired["expiry"]["error"]["code"],
                        "full_readiness": ready["readiness"],
                        "odoo_version": odoo_version,
                        "proposal_states": sorted(states),
                        "tool_names": turn_tools,
                        "writes_expected": {
                            "ambiguous": 1,
                            "happy": 1,
                            "reject": 0,
                            "stale_action": 0,
                            "xss": 0,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            if proxy is not None:
                proxy.shutdown()
                proxy.server_close()
            if proxy_thread is not None:
                proxy_thread.join(timeout=5)
            for process in reversed(processes):
                _stop(process)
            for log in logs:
                log.close()
            if created:
                with psycopg.connect(admin_dsn, autocommit=True) as connection:
                    for database_name in (odoo_db, assistant_db):
                        connection.execute(
                            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                                sql.Identifier(database_name)
                            )
                        )
                    for role in (odoo_role, assistant_role):
                        connection.execute(
                            sql.SQL("DROP ROLE IF EXISTS {}").format(
                                sql.Identifier(role)
                            )
                        )


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"M6_E2E_ERROR={error}", file=sys.stderr)
        raise SystemExit(1) from None
