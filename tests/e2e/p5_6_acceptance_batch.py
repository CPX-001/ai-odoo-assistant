#!/usr/bin/env python3
"""Run the complete P5.6 ConversationContextManager acceptance chain.

The batch intentionally crosses focused -> deterministic/full regression -> real browser
continuity without artificial manual checkpoints. A successful browser observation remains
OBSERVED_OK_NOT_AUTOMATIC_PASS until a human/agent reviews the bounded evidence.
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
BROWSER_RUNNER = ROOT / "tests" / "e2e" / "p5_6_continuity_browser.mjs"
GATE_CHECK = ROOT / "tests" / "e2e" / "p5_6_real_gate_check.py"
FOCUSED_GATE = "P5.6-ODOO-CONTEXT"
DETERMINISTIC_GATE = "P5.6-DETERMINISTIC-REGRESSION"
ADDON_GATE = "P5.6-FULL-ADDON-REGRESSION"
REAL_GATE = "P5-REAL-CONTINUITY"

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
    """A P5.6 prerequisite or gate failed."""


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


def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _run_streamed(command: list[str]) -> tuple[int, str]:
    print(f"\n$ {shlex.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
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
    sha = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise BatchError("cannot resolve exact git HEAD")
    return sha


def _require_clean_worktree() -> None:
    result = _run_capture(
        ["git", "status", "--porcelain=v1", "--untracked-files=normal"]
    )
    if result.returncode != 0:
        raise BatchError("git status failed")
    if result.stdout.strip():
        raise BatchError(
            "P5.6 acceptance requires a clean worktree so the tested SHA identifies exact content"
        )


def _parse_odoo_summary(output: str) -> dict[str, int] | None:
    matches: list[dict[str, int]] = []
    for pattern in _ODOO_SUMMARY_PATTERNS:
        for match in pattern.finditer(output):
            matches.append(
                {key: int(value) for key, value in match.groupdict().items()}
            )
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
        raise BatchError("managed P5.6 validation requires an http loopback Odoo URL")
    host = parsed.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise BatchError("managed P5.6 validation may only start Odoo on loopback")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BatchError("ODOO_AI_P5_BASE_URL must be a bare loopback origin")
    return ("127.0.0.1" if host == "localhost" else host), parsed.port or 80


def _environment() -> tuple[list[str], str, str, str, str]:
    odoo_bin = _split_command(_required_env("ODOO_BIN"))
    odoo_conf = _required_env("ODOO_CONF")
    addons_path = _required_env("ODOO_AI_ADDONS_PATH")
    database = _required_env("ODOO_AI_P5_DB")
    if not database.startswith("odoo_ai_"):
        raise BatchError("ODOO_AI_P5_DB must use the disposable odoo_ai_* prefix")
    base_url = _required_env("ODOO_AI_P5_BASE_URL").rstrip("/")
    _required_env("ODOO_AI_P5_LOGIN")
    _required_env("ODOO_AI_P5_PASSWORD")
    _loopback_server_details(base_url)
    return odoo_bin, odoo_conf, addons_path, database, base_url


def _odoo_test_args() -> list[str]:
    raw = os.environ.get("ODOO_AI_P56_ODOO_TEST_ARGS", "").strip()
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
            f"{gate} exited successfully but Odoo totals were not visible; "
            "adjust ODOO_AI_P56_ODOO_TEST_ARGS"
        )
    if summary["failed"] or summary["errors"] or summary["tests"] <= 0:
        raise BatchError(f"{gate} did not finish cleanly: {summary}")
    return {"id": gate, "result": "PASS", **summary}


def _preflight() -> tuple[str, dict[str, object]]:
    _require_clean_worktree()
    sha = _git_sha()
    _require_success(
        ["node", "--check", str(BROWSER_RUNNER)],
        label="P5.6 browser syntax",
    )
    _require_success(
        [sys.executable, str(GATE_CHECK)],
        label="P5.6 real-gate manifest",
    )
    _require_success(
        [sys.executable, "-m", "compileall", "-q", "addons/odoo_ai_assistant", "tests"],
        label="P5.6 compileall",
    )
    unit_output = _require_success(
        [sys.executable, "-m", "pytest", "-q", "tests/unit"],
        label=DETERMINISTIC_GATE,
    )
    _require_success(
        ["node", "tests/js/failure_contract_test.mjs"],
        label="P5.6 failure contract regression",
    )
    _require_success(
        ["node", "tests/js/public_activity_contract_test.mjs"],
        label="P5.6 public activity regression",
    )
    _require_success(["git", "diff", "--check"], label="git diff --check")
    return sha, {
        "id": DETERMINISTIC_GATE,
        "result": "PASS",
        "pytest_tail": unit_output.strip().splitlines()[-1] if unit_output.strip() else "",
    }


def _server_is_reachable(base_url: str, database: str, *, timeout: float = 1.5) -> bool:
    request = Request(
        f"{base_url}/web/login?db={quote(database)}",
        method="GET",
    )
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
    *,
    odoo_bin: list[str],
    odoo_conf: str,
    addons_path: str,
    database: str,
    base_url: str,
) -> tuple[subprocess.Popen[bytes], Path]:
    interface, port = _loopback_server_details(base_url)
    if _server_is_reachable(base_url, database):
        raise BatchError(
            f"{base_url} is already serving Odoo; stop the normal service before this batch"
        )
    raw_extra = os.environ.get("ODOO_AI_P56_ODOO_SERVER_ARGS", "").strip()
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
        prefix="odoo-ai-p56-server-",
        suffix=".log",
        delete=False,
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
    deadline = time.monotonic() + 60
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
        raise BatchError(f"{REAL_GATE} returned an unexpected observation state")
    for key in (
        "reconnect_follow_up",
        "exact_prior_token_recovered",
        "current_message_excluded",
        "cross_conversation_isolation",
    ):
        if observation.get(key) is not True:
            raise BatchError(f"{REAL_GATE} missing {key}=true")
    if observation.get("persisted_context_version") != 1:
        raise BatchError(f"{REAL_GATE} did not observe context format version 1")
    return {
        "id": REAL_GATE,
        "result": "OBSERVED_OK_NOT_AUTOMATIC_PASS",
        "reconnect_follow_up": True,
        "exact_prior_token_recovered": True,
        "persisted_context_version": 1,
        "current_message_excluded": True,
        "cross_conversation_isolation": True,
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
        "postgres_client": (
            _version_output(["psql", "--version"]) if shutil.which("psql") else None
        ),
        "codex": _version_output(["codex", "--version"]) if shutil.which("codex") else None,
        "playwright": _version_output(
            ["node", "-p", "require('playwright/package.json').version"]
        ),
    }


def _write_summary(path: Path | None, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path is not None:
        path.write_text(rendered, encoding="utf-8")
    print("\nP5.6 sanitized summary:")
    print(rendered)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    managed: subprocess.Popen[bytes] | None = None
    log_path: Path | None = None
    summary: dict[str, object] = {
        "phase": "P5.6",
        "result": "FAILED",
        "gates": [],
    }
    try:
        odoo_bin, odoo_conf, addons_path, database, base_url = _environment()
        sha, deterministic = _preflight()
        summary["sha"] = sha
        summary["environment"] = _environment_facts(odoo_bin)
        summary["gates"].append(deterministic)

        focused = _run_odoo_gate(
            gate=FOCUSED_GATE,
            test_tags="/odoo_ai_assistant:TestAssistantConversationContext",
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
        )
        summary["gates"].append(focused)

        addon = _run_odoo_gate(
            gate=ADDON_GATE,
            test_tags="/odoo_ai_assistant",
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
        )
        summary["gates"].append(addon)

        managed, log_path = _start_managed_server(
            odoo_bin=odoo_bin,
            odoo_conf=odoo_conf,
            addons_path=addons_path,
            database=database,
            base_url=base_url,
        )
        real = _run_real_browser_gate()
        summary["gates"].append(real)
        summary["result"] = "PASS_PENDING_EVIDENCE_REVIEW"
        return 0
    except (BatchError, OSError) as error:
        summary["error"] = str(error)[:500]
        if log_path is not None:
            summary["managed_server_log_tail_available"] = bool(_tail(log_path))
        return 1
    finally:
        if managed is not None:
            _stop_managed_server(managed)
        _write_summary(args.summary_out, summary)


if __name__ == "__main__":
    raise SystemExit(main())
