#!/usr/bin/env python3
"""Run the complete P5.5 acceptance chain as one local/real validation batch.

Formal gate ordering remains focused Odoo -> deterministic/full regression -> real provider/browser,
but a green gate does not create an artificial manual checkpoint. The runner continues immediately
until the next genuine failure or the final evidence-review boundary.

A successful real browser observation remains ``OBSERVED_OK_NOT_AUTOMATIC_PASS``. This batch therefore
ends in ``PASS_PENDING_EVIDENCE_REVIEW`` and never marks roadmap acceptance by itself.
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
BROWSER_RUNNER = ROOT / "tests" / "e2e" / "p5_5_post_effect_browser.mjs"
GATE_MANIFEST = ROOT / "tests" / "e2e" / "p5_5_real_gates.json"
FOCUSED_GATE = "P5.5-ODOO-POST-EFFECT"
DETERMINISTIC_GATE = "P5.5-DETERMINISTIC-REGRESSION"
ADDON_GATE = "P5.5-FULL-ADDON-REGRESSION"
REAL_GATE = "P5-REAL-POST-EFFECT"

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
    """A P5.5 validation prerequisite or gate failed."""


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
            "P5.5 acceptance requires a clean worktree so the tested SHA identifies exact content"
        )


def _parse_odoo_summary(output: str) -> dict[str, int] | None:
    matches: list[dict[str, int]] = []
    for pattern in _ODOO_SUMMARY_PATTERNS:
        for match in pattern.finditer(output):
            matches.append({key: int(value) for key, value in match.groupdict().items()})
    return matches[-1] if matches else None


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
        raise BatchError("managed P5.5 validation requires an http loopback Odoo URL")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise BatchError("managed P5.5 validation may only start Odoo on a loopback host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BatchError("ODOO_AI_P5_BASE_URL must be a bare loopback origin")
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
    action_id = _required_env("ODOO_AI_P5_APPROVAL_ACTION_ID")
    if not action_id.isdigit() or int(action_id) <= 0:
        raise BatchError("ODOO_AI_P5_APPROVAL_ACTION_ID must be a positive integer")
    _loopback_server_details(base_url)
    return odoo_bin, odoo_conf, addons_path, database, base_url


def _preflight() -> tuple[str, dict[str, object]]:
    _require_clean_worktree()
    sha = _git_sha()
    _require_success(["node", "--check", str(BROWSER_RUNNER)], label="P5.5 browser syntax")
    _require_success(
        [sys.executable, "-m", "json.tool", str(GATE_MANIFEST)],
        label="P5.5 real-gate manifest",
    )
    _require_success(
        [sys.executable, "-m", "compileall", "-q", "addons/odoo_ai_assistant", "tests"],
        label="P5.5 compileall",
    )
    unit_output = _require_success(
        [sys.executable, "-m", "pytest", "-q", "tests/unit"],
        label=DETERMINISTIC_GATE,
    )
    _require_success(
        ["node", "tests/js/failure_contract_test.mjs"],
        label="P5.5 failure contract regression",
    )
    _require_success(
        ["node", "tests/js/public_activity_contract_test.mjs"],
        label="P5.5 public activity regression",
    )
    _require_success(["git", "diff", "--check"], label="git diff --check")
    return sha, {
        "id": DETERMINISTIC_GATE,
        "result": "PASS",
        "pytest_tail": unit_output.strip().splitlines()[-1] if unit_output.strip() else "",
    }


def _odoo_test_args() -> list[str]:
    raw = os.environ.get("ODOO_AI_P55_ODOO_TEST_ARGS", "").strip()
    return _split_command(raw) if raw else []


def _run_odoo_gate(
    *,
    gate: str,
    test_tags: str,
    odoo_bin: list[str],
    odoo_conf: str,
    addons_path: str,
    database: str,
) -> dict[str, object]:
    command = [
        *odoo_bin,
        "-c",
        odoo_conf,
        *_odoo_test_args(),
        "-d",
        database,
        f"--addons-path={addons_path}",
        "-u",
        "odoo_ai_assistant",
        "--test-enable",
        f"--test-tags={test_tags}",
        "--stop-after-init",
        "--log-level=test",
    ]
    output = _require_success(command, label=gate)
    summary = _parse_odoo_summary(output)
    if summary is None:
        raise BatchError(
            f"{gate} exited successfully but Odoo totals were not visible; adjust ODOO_AI_P55_ODOO_TEST_ARGS"
        )
    if summary["failed"] or summary["errors"] or summary["tests"] <= 0:
        raise BatchError(f"{gate} did not finish cleanly: {summary}")
    return {"id": gate, "result": "PASS", **summary}


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
            f"{base_url} is already serving Odoo; stop the normal service before the managed P5.5 batch"
        )
    raw_extra = os.environ.get("ODOO_AI_P55_ODOO_SERVER_ARGS", "").strip()
    extra = _split_command(raw_extra) if raw_extra else []
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
        prefix="odoo-ai-p55-server-", suffix=".log", delete=False
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
            raise BatchError("managed Odoo exited before readiness\n" + _tail(log_path))
        if _server_is_reachable(base_url, database):
            return process, log_path
        time.sleep(0.5)
    _stop_managed_server(process)
    raise BatchError("managed Odoo did not become ready within 60 seconds\n" + _tail(log_path))


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
    required_true = (
        "approval_required_before_write",
        "write_barrier_observed",
        "post_effect_final_answer_observed",
        "final_marker_observed",
    )
    for key in required_true:
        if observation.get(key) is not True:
            raise BatchError(f"{REAL_GATE} missing required observation {key}=true")
    if observation.get("deterministic_completion_fallback_observed") is not False:
        raise BatchError(f"{REAL_GATE} observed deterministic completion fallback")
    if observation.get("executable_plan_proposals_after_receipt") != 0:
        raise BatchError(f"{REAL_GATE} observed a post-receipt executable plan proposal")
    if observation.get("completed_effect_steps") != 1:
        raise BatchError(f"{REAL_GATE} did not retain exactly one completed effect step")
    if observation.get("verified_effect_receipt_count") != 1:
        raise BatchError(f"{REAL_GATE} did not retain exactly one verified effect receipt")
    return {
        "id": REAL_GATE,
        "result": "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        "approval_required_before_write": True,
        "write_barrier_observed": True,
        "verified_effect_receipt_count": 1,
        "completed_effect_steps": 1,
        "post_effect_final_answer_observed": True,
        "deterministic_completion_fallback_observed": False,
        "executable_plan_proposals_after_receipt": 0,
        "rejected_post_effect_plan_attempts": observation.get("rejected_post_effect_plan_attempts"),
        "final_assistant_message_count": observation.get("final_assistant_message_count"),
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
    return {
        "python": sys.version.split()[0],
        "node": _version_output(["node", "--version"]),
        "odoo": _version_output([*odoo_bin, "--version"]),
        "postgres_client": _version_output(["psql", "--version"]) if shutil.which("psql") else None,
        "codex": _version_output(["codex", "--version"]) if shutil.which("codex") else None,
        "playwright": _version_output(
            ["node", "-e", "console.log(require('playwright/package.json').version)"]
        ),
    }


def _write_summary(path: str | None, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print("\nP5.5 acceptance batch summary:\n" + rendered, flush=True)
    if path:
        destination = Path(path).expanduser().resolve()
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"summary written to {destination}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete P5.5 acceptance chain required before P5.6 is eligible."
    )
    parser.add_argument(
        "--summary-out",
        help="optional path for sanitized batch summary; prefer a path outside the repository",
    )
    args = parser.parse_args(argv)

    try:
        odoo_bin, odoo_conf, addons_path, database, base_url = _odoo_base_command()
        sha, deterministic = _preflight()
        environment = _environment_facts(odoo_bin)

        focused = _run_odoo_gate(
            gate=FOCUSED_GATE,
            test_tags="/odoo_ai_assistant:TestPostEffectReasoning",
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
        )
        full = _run_odoo_gate(
            gate=ADDON_GATE,
            test_tags="/odoo_ai_assistant",
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
            real = _run_real_browser_gate()
        finally:
            _stop_managed_server(server)

        payload: dict[str, object] = {
            "batch": "P5.5-TO-P5.6-ACCEPTANCE",
            "tested_sha": sha,
            "result": "PASS_PENDING_EVIDENCE_REVIEW",
            "gates": [focused, deterministic, full, real],
            "environment": environment,
            "managed_server_log": str(server_log),
            "next_action": (
                "Review the sanitized real observation, record formal P5.5 evidence and move to "
                "P5.6 only if no repair changed the tested SHA."
            ),
        }
        _write_summary(args.summary_out, payload)
        return 0
    except (BatchError, OSError) as error:
        payload = {
            "batch": "P5.5-TO-P5.6-ACCEPTANCE",
            "result": "FAIL_OR_BLOCKED",
            "reason": str(error),
        }
        _write_summary(args.summary_out, payload)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
