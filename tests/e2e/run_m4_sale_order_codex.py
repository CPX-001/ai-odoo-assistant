"""Disposable real M4 runner: Chromium -> Odoo -> Assistant -> Codex -> source."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SCRIPT = REPO_ROOT / "tests/e2e/m4_sale_order_fixture.py"
BROWSER_SCRIPT = REPO_ROOT / "tests/e2e/m4_sale_order_browser.mjs"
QUESTION = "¿Por qué al confirmar este pedido se crea una tarea?"


class GateError(RuntimeError):
    pass


def _required_path(name: str, *, directory: bool = False) -> Path:
    value = os.environ.get(name, "").strip()
    path = Path(value)
    if not value or not path.is_absolute() or not path.exists():
        raise GateError(f"{name} must be an existing absolute path")
    if directory != path.is_dir():
        kind = "directory" if directory else "file"
        raise GateError(f"{name} must be an existing {kind}")
    return path.resolve() if directory else path.absolute()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _run(
    argv: list[str],
    *,
    env: dict[str, str],
    cwd: Path = REPO_ROOT,
    stdin: Path | None = None,
    timeout: float = 300,
) -> str:
    stream = stdin.open("rb") if stdin is not None else None
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=stream,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        if stream is not None:
            stream.close()
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-30:])
        raise GateError(f"command failed with exit {result.returncode}:\n{tail}")
    return result.stdout


def _start(
    argv: list[str], *, env: dict[str, str], cwd: Path, log_path: Path
) -> tuple[subprocess.Popen[bytes], Any]:
    log = log_path.open("wb")
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process, log


def _stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def _wait_url(url: str, *, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise GateError("HTTP process did not become ready")


def _json_request(
    url: str,
    *,
    secret: str,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Odoo-AI-Shared-Secret": secret,
        },
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def _prefixed_json(output: str, prefix: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        if line.startswith(prefix):
            return json.loads(line.removeprefix(prefix))
    raise GateError(f"runner output did not contain {prefix}")


def _browser(
    *,
    work: Path,
    playwright_root: Path,
    node: Path,
    env: dict[str, str],
    mode: str,
) -> dict[str, Any]:
    browser_copy = work / f"m4-browser-{mode}.mjs"
    shutil.copy2(BROWSER_SCRIPT, browser_copy)
    node_modules = work / "node_modules"
    if not node_modules.exists():
        node_modules.symlink_to(playwright_root / "node_modules", target_is_directory=True)
    browser_env = dict(env)
    browser_env["M4_EXPECT_MODE"] = mode
    output = _run([str(node), str(browser_copy)], env=browser_env, cwd=work, timeout=300)
    return _prefixed_json(output, "M4_E2E_BROWSER=")


def _sanitized_log_tail(path: Path, forbidden: tuple[str, ...]) -> str:
    if not path.is_file():
        return "assistant log unavailable"
    value = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
    for item in forbidden:
        if item:
            value = value.replace(item, "[redacted]")
    return value


def _database_uri(
    parsed: urllib.parse.SplitResult, user: str, password: str, database: str
) -> str:
    host = parsed.hostname or ""
    port = parsed.port or 5432
    return (
        "postgresql+psycopg://"
        f"{urllib.parse.quote(user)}:{urllib.parse.quote(password)}@{host}:{port}/{database}"
    )


def main() -> None:
    odoo_python = _required_path("M4_ODOO_PYTHON")
    odoo_bin = _required_path("M4_ODOO_BIN")
    odoo_core_addons = _required_path("M4_ODOO_CORE_ADDONS", directory=True)
    codex = _required_path("M4_CODEX_EXECUTABLE")
    playwright_root = _required_path("M4_PLAYWRIGHT_ROOT", directory=True)
    node = _required_path("M4_NODE")
    if not (playwright_root / "node_modules/playwright").is_dir():
        raise GateError("M4_PLAYWRIGHT_ROOT must contain node_modules/playwright")

    admin_dsn = os.environ.get("M4_POSTGRES_ADMIN_DSN", "").strip()
    parsed_admin = urllib.parse.urlsplit(admin_dsn)
    if (
        parsed_admin.scheme not in {"postgresql", "postgres"}
        or not parsed_admin.hostname
        or not parsed_admin.path.strip("/")
    ):
        raise GateError("M4_POSTGRES_ADMIN_DSN must be a PostgreSQL URI")

    suffix = secrets.token_hex(5)
    odoo_role = f"m4_odoo_{suffix}"
    assistant_role = f"m4_assistant_{suffix}"
    odoo_db = f"m4_odoo_{suffix}"
    assistant_db = f"m4_assistant_{suffix}"
    odoo_password = secrets.token_urlsafe(24)
    assistant_password = secrets.token_urlsafe(24)
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[Any] = []
    created = False

    with tempfile.TemporaryDirectory(prefix="odoo-ai-m4-e2e-") as raw_work:
        work = Path(raw_work).resolve()
        fixture_addons = work / "fixture-addons"
        fixture_addons.mkdir()
        shutil.copytree(
            REPO_ROOT / "tests/fixtures/odoo18/odoo_ai_m3_sale_project",
            fixture_addons / "odoo_ai_m3_sale_project",
        )
        log_file = work / "m4-odoo.log"
        shutil.copy2(REPO_ROOT / "tests/fixtures/logs/m3_odoo_traceback.txt", log_file)
        shared_secret = "m4-shared-" + secrets.token_urlsafe(48)
        delegation_secret = "m4-delegation-" + secrets.token_urlsafe(48)
        shared_file = work / "shared-secret"
        delegation_file = work / "delegation-secret"
        shared_file.write_text(shared_secret + "\n", encoding="utf-8")
        delegation_file.write_text(delegation_secret + "\n", encoding="utf-8")
        shared_file.chmod(0o600)
        delegation_file.chmod(0o600)
        pgpass = work / "pgpass"
        pgpass.write_text(
            f"{parsed_admin.hostname}:{parsed_admin.port or 5432}:*:{odoo_role}:{odoo_password}\n",
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
                for database, owner in (
                    (odoo_db, odoo_role),
                    (assistant_db, assistant_role),
                ):
                    connection.execute(
                        sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                            sql.Identifier(database), sql.Identifier(owner)
                        )
                    )
                    connection.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                            sql.Identifier(database)
                        )
                    )
                    connection.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(database), sql.Identifier(owner)
                        )
                    )
            forbidden_odoo_dsn = _database_uri(
                parsed_admin, assistant_role, assistant_password, odoo_db
            ).replace("postgresql+psycopg://", "postgresql://")
            try:
                psycopg.connect(forbidden_odoo_dsn).close()
            except psycopg.OperationalError:
                pass
            else:
                raise GateError("Assistant role unexpectedly connected to the Odoo DB")

            odoo_port = _free_port()
            assistant_port = _free_port()
            odoo_url = f"http://127.0.0.1:{odoo_port}"
            assistant_url = f"http://127.0.0.1:{assistant_port}"
            addons_path = ",".join(
                (str(odoo_core_addons), str(REPO_ROOT / "addons"), str(fixture_addons))
            )
            common_env = dict(os.environ)
            common_env.update(
                {
                    "ODOO_AI_DELEGATION_SECRET_FILE": str(delegation_file),
                    "ODOO_AI_SERVICE_URL": assistant_url,
                    "ODOO_AI_SHARED_SECRET_FILE": str(shared_file),
                    "ODOO_AI_TURN_TIMEOUT_SECONDS": "210",
                    "PGPASSFILE": str(pgpass),
                }
            )
            odoo_db_args = [
                f"--database={odoo_db}",
                f"--db_host={parsed_admin.hostname}",
                f"--db_port={parsed_admin.port or 5432}",
                f"--db_user={odoo_role}",
                f"--addons-path={addons_path}",
            ]
            _run(
                [
                    str(odoo_python),
                    str(odoo_bin),
                    *odoo_db_args,
                    "--init=odoo_ai_assistant,odoo_ai_m3_sale_project",
                    "--without-demo=all",
                    "--stop-after-init",
                ],
                env=common_env,
                timeout=300,
            )

            fixture_env = dict(common_env)
            fixture_env.update(
                {
                    "M4_E2E_LOGIN": f"m4-sales-{suffix}",
                    "M4_E2E_PASSWORD": secrets.token_urlsafe(18),
                }
            )
            fixture_output = _run(
                [str(odoo_python), str(odoo_bin), "shell", *odoo_db_args, "--no-http"],
                env=fixture_env,
                stdin=FIXTURE_SCRIPT,
                timeout=180,
            )
            fixture = _prefixed_json(fixture_output, "M4_E2E_FIXTURE=")

            odoo_process, odoo_log = _start(
                [
                    str(odoo_python),
                    str(odoo_bin),
                    *odoo_db_args,
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

            assistant_url_db = _database_uri(
                parsed_admin, assistant_role, assistant_password, assistant_db
            )
            service_env = dict(common_env)
            service_env.update(
                {
                    "ODOO_AI_ALEMBIC_CONFIG": str(REPO_ROOT / "alembic.ini"),
                    "ODOO_AI_CODEX_EXECUTABLE": str(codex),
                    "ODOO_AI_CODEX_EXPERIMENTAL_API": "1",
                    "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS": "180",
                    "ODOO_AI_DATABASE_NAME": assistant_db,
                    "ODOO_AI_DATABASE_URL": assistant_url_db,
                    "ODOO_AI_LOG_FILE": str(log_file),
                    "ODOO_AI_ODOO_BASE_URL": odoo_url,
                    "ODOO_AI_PORT": str(assistant_port),
                    "ODOO_AI_SOURCE_ROOTS": json.dumps(
                        [str(fixture_addons), str(REPO_ROOT / "addons")]
                    ),
                }
            )
            _run(
                [str(REPO_ROOT / ".venv/bin/python"), "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), "upgrade", "head"],
                env=service_env,
                timeout=120,
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
                payload={
                    "terms": ["action_confirm"],
                    "max_lines": 20,
                    "max_bytes": 8_192,
                },
            )
            ready = _json_request(
                f"{assistant_url}/v1/admin/status", secret=shared_secret
            )
            if ready.get("readiness") != "FULLY_READY":
                raise GateError("FULLY_READY was not demonstrated")

            browser_env = dict(fixture_env)
            browser_env.update(
                {
                    "M4_ALLOWED_ORDER_ID": str(fixture["allowed_order_id"]),
                    "M4_ALLOWED_ORDER_NAME": str(fixture["allowed_order_name"]),
                    "M4_ASSISTANT_BASE_URL": assistant_url,
                    "M4_DENIED_ORDER_ID": str(fixture["denied_order_id"]),
                    "M4_FORBIDDEN_VALUES": ",".join(
                        (
                            shared_secret,
                            delegation_secret,
                            assistant_password,
                            odoo_password,
                            str(fixture_addons),
                        )
                    ),
                    "M4_ODOO_BASE_URL": odoo_url,
                    "M4_ODOO_DATABASE": odoo_db,
                }
            )
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
                diagnostic = _sanitized_log_tail(
                    work / "assistant-service.log",
                    (
                        shared_secret,
                        delegation_secret,
                        assistant_password,
                        odoo_password,
                        str(fixture_addons),
                        QUESTION,
                    ),
                )
                raise GateError(f"{error}\nassistant log tail:\n{diagnostic}") from None
            response = positive["response"]

            verify_env = dict(fixture_env)
            verify_env.update(
                {
                    "M4_ALLOWED_ORDER_ID": str(fixture["allowed_order_id"]),
                    "M4_E2E_VERIFY_EFFECT": "1",
                }
            )
            effect_output = _run(
                [str(odoo_python), str(odoo_bin), "shell", *odoo_db_args, "--no-http"],
                env=verify_env,
                stdin=FIXTURE_SCRIPT,
                timeout=180,
            )
            effect = _prefixed_json(effect_output, "M4_E2E_EFFECT=")

            turn_id = response["turn_id"]
            assistant_psycopg_dsn = assistant_url_db.replace(
                "postgresql+psycopg://", "postgresql://"
            )
            with psycopg.connect(assistant_psycopg_dsn) as connection:
                rows = connection.execute(
                    "SELECT event_name, status, attributes FROM trace_event "
                    "WHERE trace_id = %s ORDER BY sequence",
                    (turn_id,),
                ).fetchall()
            tool_sequence = [
                name
                for row in rows
                if row[0] == "tool.completed"
                and row[1] == "ok"
                and isinstance(name := row[2].get("tool_name"), str)
            ]
            if "source.read_excerpt" not in tool_sequence or not any(
                name in {"source.find_symbol", "source.find_model_extensions"}
                for name in tool_sequence
            ):
                raise GateError("real Codex did not complete the required source tool sequence")
            serialized_trace = json.dumps(rows, default=str, ensure_ascii=False)
            for forbidden in (
                shared_secret,
                delegation_secret,
                assistant_password,
                odoo_password,
                str(fixture_addons),
                QUESTION,
            ):
                if forbidden in serialized_trace:
                    raise GateError("a canary leaked into trace metadata")

            fixture_source = (
                fixture_addons / "odoo_ai_m3_sale_project/models/sale_order.py"
            )
            fixture_source.write_text(
                fixture_source.read_text(encoding="utf-8")
                + "\n# M4 stale fingerprint probe\n",
                encoding="utf-8",
            )
            stale = _browser(
                work=work,
                playwright_root=playwright_root,
                node=node,
                env=browser_env,
                mode="stale",
            )

            _stop(service_process)
            service_env["ODOO_AI_CODEX_EXECUTABLE"] = str(work / "missing-codex")
            degraded_process, degraded_log = _start(
                [str(REPO_ROOT / ".venv/bin/python"), "-m", "odoo_ai.api"],
                env=service_env,
                cwd=REPO_ROOT / "service",
                log_path=work / "assistant-degraded.log",
            )
            processes.append(degraded_process)
            logs.append(degraded_log)
            _wait_url(f"{assistant_url}/health")
            degraded = _json_request(
                f"{assistant_url}/v1/admin/status", secret=shared_secret
            )
            if (
                degraded.get("readiness") != "DEGRADED"
                or degraded.get("components", {})
                .get("reasoning_engine", {})
                .get("detail")
                != "runtime_missing"
            ):
                raise GateError("missing Codex did not produce actionable DEGRADED status")
            unavailable = _browser(
                work=work,
                playwright_root=playwright_root,
                node=node,
                env=browser_env,
                mode="engine_unavailable",
            )

            source_citation = next(
                item for item in response["citations"] if item["kind"] == "source"
            )
            record_citation = next(
                item for item in response["citations"] if item["kind"] == "record"
            )
            print(
                "M4_E2E_RESULT="
                + json.dumps(
                    {
                        "answer_summary": response["answer"][:280],
                        "effect": effect,
                        "engine_unavailable_error": unavailable["response"]["error"]["code"],
                        "full_readiness": ready["readiness"],
                        "missing_codex_readiness": degraded["readiness"],
                        "question": QUESTION,
                        "record_citation": record_citation,
                        "source_citation": source_citation,
                        "stale_result": (
                            "bounded_answer"
                            if stale["response"].get("ok")
                            else stale["response"]["error"]["code"]
                        ),
                        "tool_counts": {
                            name: tool_sequence.count(name) for name in sorted(set(tool_sequence))
                        },
                        "tool_sequence": tool_sequence,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        finally:
            for process in reversed(processes):
                _stop(process)
            for log in logs:
                log.close()
            if created:
                with psycopg.connect(admin_dsn, autocommit=True) as connection:
                    for database in (odoo_db, assistant_db):
                        connection.execute(
                            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                                sql.Identifier(database)
                            )
                        )
                    for role in (odoo_role, assistant_role):
                        connection.execute(
                            sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                        )


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"M4_E2E_ERROR={error}", file=sys.stderr)
        raise SystemExit(1) from None
