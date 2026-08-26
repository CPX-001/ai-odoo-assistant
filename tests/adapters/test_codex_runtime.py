import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from odoo_ai.adapters import (
    APP_SERVER_PROTOCOL,
    CodexAppServerClient,
    CodexProbeState,
    CodexProtocolError,
    CodexRuntimeConfigurationError,
    CodexRuntimeProcessError,
    CodexRuntimeSettings,
    CodexRuntimeTimeoutError,
    probe_codex_readiness,
    probe_codex_runtime,
)


def _fake_codex(tmp_path: Path, body: str) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import os\n"
        "import signal\n"
        "import sys\n"
        "import time\n"
        f"{body}\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _valid_handshake(*, after_initialized: str = "") -> str:
    return (
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': request['id'], 'result': {"
        "'codexHome': os.getcwd(), 'platformFamily': 'unix', "
        "'platformOs': 'linux', 'userAgent': 'fake-codex/1.2.3'}}), flush=True)\n"
        "initialized = json.loads(sys.stdin.readline())\n"
        f"{after_initialized}\n"
        "sys.stdin.read()"
    )


def test_handshake_argv_environment_cwd_policy_and_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = tmp_path / "isolated workspace"
    isolated.mkdir()
    observed = tmp_path / "observed.json"
    after = (
        f"open({str(observed)!r}, 'w', encoding='utf-8').write(json.dumps({{"
        "'argv': sys.argv[1:], 'cwd': os.getcwd(), "
        "'initialized': initialized, "
        "'secret_visible': 'ODOO_AI_SHARED_SECRET_FILE' in os.environ}))"
    )
    executable = _fake_codex(tmp_path, _valid_handshake(after_initialized=after))
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", "/private/shared-secret")

    async def run() -> None:
        client = await CodexAppServerClient.start(
            CodexRuntimeSettings(executable=executable, isolated_cwd=isolated)
        )
        assert client.server_info is not None
        assert client.server_info.user_agent == "fake-codex/1.2.3"
        assert client.thread_policy.start_params() == {
            "approvalPolicy": "never",
            "cwd": str(isolated.resolve()),
            "dynamicTools": [],
            "environments": [],
            "ephemeral": True,
            "runtimeWorkspaceRoots": [],
            "sandbox": "read-only",
        }
        assert client.stderr_metadata == {
            "captured_bytes": 0,
            "total_bytes": 0,
            "truncated": False,
        }
        await client.close()

    asyncio.run(run())
    captured = json.loads(observed.read_text(encoding="utf-8"))
    assert captured == {
        "argv": [
            "app-server",
            "--stdio",
            "--strict-config",
            "--config",
            "mcp_servers={}",
        ],
        "cwd": str(isolated.resolve()),
        "initialized": {"method": "initialized"},
        "secret_visible": False,
    }


def test_runtime_uses_credential_only_temporary_codex_home(tmp_path: Path) -> None:
    source_home = tmp_path / "source-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"token":"test-only"}', encoding="utf-8")
    (source_home / "config.toml").write_text(
        '[mcp_servers.untrusted]\nurl="https://example.invalid"\n',
        encoding="utf-8",
    )
    observed = tmp_path / "observed-home.json"
    after = (
        "codex_home = os.environ['CODEX_HOME']\n"
        f"open({str(observed)!r}, 'w', encoding='utf-8').write(json.dumps({{"
        "'home': codex_home, "
        "'auth': open(os.path.join(codex_home, 'auth.json'), encoding='utf-8').read(), "
        "'config_exists': os.path.exists(os.path.join(codex_home, 'config.toml'))}))"
    )
    executable = _fake_codex(tmp_path, _valid_handshake(after_initialized=after))

    async def run() -> None:
        client = await CodexAppServerClient.start(
            CodexRuntimeSettings(executable=executable, codex_home=source_home)
        )
        await client.close()

    asyncio.run(run())
    captured = json.loads(observed.read_text(encoding="utf-8"))
    isolated_home = Path(captured["home"])
    assert isolated_home != source_home
    assert captured["auth"] == '{"token":"test-only"}'
    assert captured["config_exists"] is False
    assert not isolated_home.exists()


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        ("{'id': request['id'] + 1, 'result': {}}", "codex_response_id_mismatch"),
        ("'not-json'", "codex_response_malformed"),
    ],
)
def test_handshake_fails_closed_for_wrong_id_or_malformed_frame(
    tmp_path: Path, response: str, error_code: str
) -> None:
    executable = _fake_codex(
        tmp_path,
        "request = json.loads(sys.stdin.readline())\n"
        f"print(json.dumps({response}), flush=True)\n"
        "sys.stdin.read()",
    )

    async def run() -> None:
        with pytest.raises(CodexProtocolError, match=error_code):
            await CodexAppServerClient.start(
                CodexRuntimeSettings(executable=executable, startup_timeout_seconds=1)
            )

    asyncio.run(run())


def test_oversized_stdout_frame_is_rejected(tmp_path: Path) -> None:
    executable = _fake_codex(
        tmp_path,
        "sys.stdin.readline()\n"
        "sys.stdout.write('x' * 4096 + '\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdin.read()",
    )

    async def run() -> None:
        with pytest.raises(CodexProtocolError, match="codex_response_frame_too_large"):
            await CodexAppServerClient.start(
                CodexRuntimeSettings(executable=executable, max_frame_bytes=1024)
            )

    asyncio.run(run())


def test_cumulative_stdout_budget_is_rejected(tmp_path: Path) -> None:
    executable = _fake_codex(
        tmp_path,
        "first = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': first['id'], 'result': {"
        "'platformFamily': 'u' * 470, 'platformOs': 'linux', "
        "'userAgent': 'fake-codex/1.2.3'}}), flush=True)\n"
        "json.loads(sys.stdin.readline())\n"
        "second = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'id': second['id'], 'result': {'x': 'y' * 470}}), flush=True)\n"
        "sys.stdin.read()",
    )

    async def run() -> None:
        client = await CodexAppServerClient.start(
            CodexRuntimeSettings(
                executable=executable,
                max_frame_bytes=1024,
                max_stdout_bytes=1024,
            )
        )
        try:
            with pytest.raises(
                CodexProtocolError, match="codex_stdout_budget_exceeded"
            ):
                await client.request("test", {})
        finally:
            await client.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("body", "error_type", "error_code"),
    [
        (
            "sys.stdin.readline()\ntime.sleep(2)",
            CodexRuntimeTimeoutError,
            "codex_read_timeout",
        ),
        (
            "sys.stdin.readline()",
            CodexRuntimeProcessError,
            "codex_process_eof",
        ),
    ],
)
def test_startup_timeout_and_eof_are_typed(
    tmp_path: Path,
    body: str,
    error_type: type[Exception],
    error_code: str,
) -> None:
    executable = _fake_codex(tmp_path, body)

    async def run() -> None:
        with pytest.raises(error_type, match=error_code):
            await CodexAppServerClient.start(
                CodexRuntimeSettings(
                    executable=executable,
                    startup_timeout_seconds=0.1,
                    shutdown_timeout_seconds=0.1,
                )
            )

    asyncio.run(run())


def test_probe_states_and_stderr_are_sanitized(tmp_path: Path) -> None:
    missing = tmp_path / "missing-codex"
    failing = _fake_codex(
        tmp_path,
        "sys.stderr.write('/private/auth.json token=raw-secret-value\\n')\n"
        "sys.stderr.flush()\n"
        "sys.stdin.readline()\n"
        "print('malformed', flush=True)",
    )

    async def run() -> None:
        unconfigured = await probe_codex_runtime(CodexRuntimeSettings(executable=None))
        not_found = await probe_codex_runtime(CodexRuntimeSettings(executable=missing))
        failed = await probe_codex_runtime(CodexRuntimeSettings(executable=failing))
        assert unconfigured.state is CodexProbeState.NOT_CONFIGURED
        assert not_found.state is CodexProbeState.NOT_FOUND
        assert failed.state is CodexProbeState.HANDSHAKE_FAILED
        assert failed.error_code == "codex_response_malformed"
        assert "auth.json" not in repr(failed)
        assert "raw-secret-value" not in repr(failed)

    asyncio.run(run())


def test_probe_reports_protocol_without_claiming_auth_or_model(tmp_path: Path) -> None:
    executable = _fake_codex(tmp_path, _valid_handshake())

    async def run() -> None:
        result = await probe_codex_runtime(CodexRuntimeSettings(executable=executable))
        assert result.state is CodexProbeState.COMPATIBLE
        assert result.protocol == APP_SERVER_PROTOCOL
        assert result.runtime_version == "1.2.3"
        assert result.auth_state == "unknown"
        assert result.model_state == "unknown"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("account", "requires_auth", "expected"),
    [
        ({"type": "chatgpt"}, True, "available"),
        (None, True, "unavailable"),
        (None, False, "not_required"),
    ],
)
def test_readiness_probe_checks_account_without_starting_a_turn(
    tmp_path: Path,
    account: dict[str, str] | None,
    requires_auth: bool,
    expected: str,
) -> None:
    observed = tmp_path / "methods.json"
    after = (
        "methods = []\n"
        "account_request = json.loads(sys.stdin.readline())\n"
        "methods.append(account_request['method'])\n"
        "print(json.dumps({'id': account_request['id'], 'result': {"
        f"'account': {account!r}, 'requiresOpenaiAuth': {requires_auth!r}"
        "}}), flush=True)\n"
        f"open({str(observed)!r}, 'w', encoding='utf-8').write(json.dumps(methods))"
    )
    executable = _fake_codex(tmp_path, _valid_handshake(after_initialized=after))

    async def run() -> None:
        result = await probe_codex_readiness(
            CodexRuntimeSettings(executable=executable, model="configured-model")
        )
        assert result.state is CodexProbeState.COMPATIBLE
        assert result.auth_state == expected
        assert result.model_state == "configured"
        assert result.model == "configured-model"

    asyncio.run(run())
    assert json.loads(observed.read_text(encoding="utf-8")) == ["account/read"]


def test_experimental_api_flag_is_explicit_and_strict() -> None:
    assert CodexRuntimeSettings.from_env(
        {"ODOO_AI_CODEX_EXPERIMENTAL_API": "true"}
    ).experimental_api
    assert not CodexRuntimeSettings.from_env({}).experimental_api
    with pytest.raises(
        CodexRuntimeConfigurationError, match="codex_boolean_setting_invalid"
    ):
        CodexRuntimeSettings.from_env({"ODOO_AI_CODEX_EXPERIMENTAL_API": "perhaps"})


def test_shutdown_kills_process_that_ignores_eof_and_term(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    executable = _fake_codex(
        tmp_path,
        _valid_handshake(
            after_initialized=(
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))"
            )
        )
        + "\nwhile True: time.sleep(1)",
    )

    async def run() -> None:
        client = await CodexAppServerClient.start(
            CodexRuntimeSettings(
                executable=executable,
                shutdown_timeout_seconds=0.1,
            )
        )
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_file.exists()
        await client.close()

    asyncio.run(run())
    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
