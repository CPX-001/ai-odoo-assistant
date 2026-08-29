#!/usr/bin/env python3
"""Run the remaining P5.3 acceptance gates as one local validation batch.

This runner deliberately keeps the two formal validation IDs separate while executing them
in one command. It first runs the complete Odoo addon regression with ``--stop-after-init``;
only after that deterministic boundary passes does it start an isolated loopback Odoo server
and execute the real Chromium settings-snapshot gate.

The real browser runner still prints ``OBSERVED_OK_NOT_AUTOMATIC_PASS``. This batch therefore
ends in ``PASS_PENDING_EVIDENCE_REVIEW`` rather than silently converting an observation into
formal roadmap acceptance. A human/Codex validation run must review the sanitized observation,
record evidence, and then advance ``EXECUTION_STATE.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BROWSER_RUNNER = ROOT / "tests" / "e2e" / "p5_3_settings_snapshot_browser.mjs"
GATE_MANIFEST = ROOT / "tests" / "e2e" / "p5_3_real_gates.json"
REAL_GATE = "P5-REAL-SETTINGS-SNAPSHOT"
ADDON_GATE = "P5.3-FULL-ADDON-REGRESSION"

_ODOO_SUMMARY_PATTERNS = (
    re.compile(
        r"(?P<failed>\d+)\s+failed,\s+(?P<errors>\d+)\s+error\(s\)\s+of\s+"
        r"(?P<tests>\d+)\s+tests",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<tests>\d+)\s+tests[^\n]*?(?P<failed>\d+)\s+failed[^\n]*?"
        r"(?P<errors>\d+)\s+errors?",
        re.IGNORECASE,
    ),
)


class BatchError(RuntimeError):
    """A validation prerequisite or gate failed."""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BatchError(f"{name} is required")
    return value


def _split_command(value: str) -> list[str]:
    parts = shlex.split(value)
    if not parts:
        raise BatchError("empty command")
    return parts


def _run_capture(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _run_streamed(command: list[str], *, cwd: Path = ROOT) -> tuple[int, str]:
    print(f"\n$ {shlex.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert process.stdout is not None
    lines: list[str] = []
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return process.wait(), "".join(lines)


def _require_success(command: list[str], *, label: str) -> str:
    returncode, output = _run_streamed(command)
    if returncode != 0:
        raise BatchError(f"{label} failed with exit code {returncode}")
    return output


def _git_sha() -> str:
    result = _run_capture(["git", "rev-parse", "HEAD"])
    if result.returncode != 0:
        raise BatchError("cannot resolve git HEAD")
    sha = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise BatchError("git HEAD is not a full commit SHA")
    return sha


def _require_clean_worktree() -> None:
    result = _run_capture(["git", "status", "--porcelain=v1", "--untracked-files=normal"])
    if result.returncode != 0:
        raise BatchError("git status failed")
    if result.stdout.strip():
        raise BatchError(
            "validation requires a clean worktree so the tested SHA exactly identifies the content"
        )


def _preflight() -> str:
    _require_clean_worktree()
    sha = _git_sha()
    _require_success(["node", "--check", str(BROWSER_RUNNER)], label="browser runner syntax")
    _require_success(
        [sys.executable, "-m", "json.tool", str(GATE_MANIFEST)],
        label="P5.3 real-gate manifest",
    )
    _require_success(["git", "diff", "--check"], label="git diff --check")
    return sha


def _parse_odoo_summary(output: str) -> dict[str, int] | None:
    matches: list[dict[str, int]] = []
    for pattern in _ODOO_SUMMARY_PATTERNS:
        for match in pattern.finditer(output):
            matches.append({key: int(value) for key, value in match.groupdict().items()})
    if not matches:
        return None
    return matches[-1]


def _parse_browser_observation(output: str) -> dict[str, object] | None:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("gate") == REAL_GATE:
            return payload
    return None


def _loopback_server_details(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        raise BatchError("managed P5.3 validation requires an http loopback Odoo URL")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise BatchError("managed P5.3 validation may only start Odoo on a loopback host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BatchError("ODOO_AI_P5_BASE_URL must be a bare origin such as http://127.0.0.1:8069")
    port = parsed.port or 80
    interface = "127.0.0.1" if host == "localhost" else host
    return interface, port


def _odoo_base_command() -> tuple[list[str], str, str, str, str]:
    odoo_bin = _split_command(_required_env("ODOO_BIN"))
    odoo_conf = _required_env("ODOO_CONF")
    addons_path = _required_env("ODOO_AI_ADDONS_PATH")
    database = _required_env("ODOO_AI_P5_DB")
    if not database.startswith("odoo_ai_"):
        raise BatchError("ODOO_AI_P5_DB must use the disposable odoo_ai_* prefix")
    base_url = _required_env("ODOO_AI_P5_BASE_URL").rstrip("/")
    _required_env("ODOO_AI_P5_LOGIN")
    _required_env("ODOO_AI_P5_PASSWORD")
    return odoo_bin, odoo_conf, addons_path, database, base_url


def _run_full_addon_regression(
    *, odoo_bin: list[str], odoo_conf: str, addons_path: str, database: str
) -> dict[str, object]:
    extra = _split_command(os.environ["ODOO_AI_P53_ODOO_TEST_ARGS"]) if os.environ.get(
        "ODOO_AI_P53_ODOO_TEST_ARGS", ""
    ).strip() else []
    command = [
        *odoo_bin,
        "-c",
        odoo_conf,
        *extra,
        "-d",
        database,
        f"--addons-path={addons_path}",
        "-u",
        "odoo_ai_assistant",
        "--test-enable",
        "--test-tags=/odoo_ai_assistant",
        "--stop-after-init",
        "--log-level=test",
    ]
    output = _require_success(command, label=ADDON_GATE)
    summary = _parse_odoo_summary(output)
    if summary is None:
        raise BatchError(
            f"{ADDON_GATE} exited successfully but its Odoo test totals could not be parsed"
        )
    if summary["failed"] != 0 or summary["errors"] != 0 or summary["tests"] <= 0:
        raise BatchError(f"{ADDON_GATE} did not finish cleanly: {summary}")
    return {"id": ADDON_GATE, "result": "PASS", **summary}


def _server_is_reachable(base_url: str, database: str, *, timeout: float = 1.5) -> bool:
    url = f"{base_url}/web/login?db={quote(database)}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 500
    except HTTPError as error:
        return 200 <= error.code < 500
    except (URLError, TimeoutError, OSError):
        return False


def _tail(path: Path, *, lines: int = 120) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def _start_managed_server(
    *, odoo_bin: list[str], odoo_conf: str, addons_path: str, database: str, base_url: str
) -> tuple[subprocess.Popen[bytes], Path]:
    interface, port = _loopback_server_details(base_url)
    if _server_is_reachable(base_url, database):
        raise BatchError(
            f"{base_url} is already serving Odoo; stop the existing service before the managed batch"
        )
    extra = _split_command(os.environ["ODOO_AI_P53_ODOO_SERVER_ARGS"]) if os.environ.get(
        "ODOO_AI_P53_ODOO_SERVER_ARGS", ""
    ).strip() else []
    command = [
        *odoo_bin,
        "-c",
        odoo_conf,
        *extra,
        "-d",
        database,
        f"--addons-path={addons_path}",
        f"--http-interface={interface}",
        f"--http-port={port}",
        "--workers=0",
        "--max-cron-threads=2",
    ]
    log_file = tempfile.NamedTemporaryFile(
        prefix="odoo-ai-p53-server-", suffix=".log", delete=False
    )
    log_path = Path(log_file.name)
    print(f"\n$ {shlex.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    log_file.close()
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BatchError(
                "managed Odoo server exited before becoming ready\n" + _tail(log_path)
            )
        if _server_is_reachable(base_url, database):
            return process, log_path
        time.sleep(0.5)
    _stop_managed_server(process)
    raise BatchError("managed Odoo server did not become ready within 60 seconds\n" + _tail(log_path))


def _stop_managed_server(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _run_real_browser_gate() -> dict[str, object]:
    output = _require_success(
        ["node", str(BROWSER_RUNNER), "--gate", REAL_GATE],
        label=REAL_GATE,
    )
    observation = _parse_browser_observation(output)
    if observation is None:
        raise BatchError(f"{REAL_GATE} produced no recognizable observation payload")
    if observation.get("result") != "OBSERVED_OK_NOT_AUTOMATIC_PASS":
        raise BatchError(f"{REAL_GATE} did not report the expected observation result")
    return {
        "id": REAL_GATE,
        "result": "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        "snapshot_format": observation.get("snapshot_format"),
        "original_model": observation.get("original_model"),
        "next_model": observation.get("next_model"),
        "original_profile": observation.get("original_profile"),
        "next_profile": observation.get("next_profile"),
    }


def _version_output(command: list[str]) -> str | None:
    try:
        result = _run_capture(command)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[0][:300] if lines else None


def _environment_facts(odoo_bin: list[str]) -> dict[str, object]:
    facts: dict[str, object] = {
        "python": sys.version.split()[0],
        "node": _version_output(["node", "--version"]),
        "odoo": _version_output([*odoo_bin, "--version"]),
        "postgres_client": _version_output(["psql", "--version"]) if shutil.which("psql") else None,
        "codex": _version_output(["codex", "--version"]) if shutil.which("codex") else None,
        "playwright": _version_output(
            ["node", "-e", "console.log(require('playwright/package.json').version)"]
        ),
    }
    return facts


def _write_summary(path: str | None, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print("\nP5.3 acceptance batch summary:\n" + rendered, flush=True)
    if path:
        destination = Path(path).expanduser().resolve()
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"summary written to {destination}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the remaining P5.3 gates required before P5.4 is eligible."
    )
    parser.add_argument(
        "--summary-out",
        help="optional path for the sanitized batch summary; prefer a path outside the repository",
    )
    args = parser.parse_args(argv)

    try:
        odoo_bin, odoo_conf, addons_path, database, base_url = _odoo_base_command()
        sha = _preflight()
        environment = _environment_facts(odoo_bin)

        addon_result = _run_full_addon_regression(
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
        )

        server, server_log = _start_managed_server(
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
            base_url=base_url,
        )
        try:
            browser_result = _run_real_browser_gate()
        finally:
            _stop_managed_server(server)

        payload: dict[str, object] = {
            "batch": "P5.3-TO-P5.4-ACCEPTANCE",
            "tested_sha": sha,
            "result": "PASS_PENDING_EVIDENCE_REVIEW",
            "gates": [addon_result, browser_result],
            "environment": environment,
            "managed_server_log": str(server_log),
            "next_action": (
                "Review the sanitized browser observation, record formal evidence, mark P5.3 COMPLETE "
                "and move EXECUTION_STATE.md to P5.4 READY only if no repair changed the tested SHA."
            ),
        }
        _write_summary(args.summary_out, payload)
        return 0
    except BatchError as error:
        print(f"\nP5.3 acceptance batch FAILED: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
