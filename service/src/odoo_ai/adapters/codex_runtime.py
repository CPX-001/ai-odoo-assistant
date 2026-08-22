"""Bounded stdio lifecycle for the versioned Codex App Server adapter."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import tempfile
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self, cast

CODEX_EXECUTABLE_ENV = "ODOO_AI_CODEX_EXECUTABLE"
CODEX_HOME_OVERRIDE_ENV = "ODOO_AI_CODEX_HOME"
CODEX_MODEL_ENV = "ODOO_AI_CODEX_MODEL"
CODEX_ISOLATED_CWD_ENV = "ODOO_AI_CODEX_ISOLATED_CWD"
CODEX_STARTUP_TIMEOUT_ENV = "ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS"
CODEX_TURN_TIMEOUT_ENV = "ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS"
CODEX_EXPERIMENTAL_API_ENV = "ODOO_AI_CODEX_EXPERIMENTAL_API"

APP_SERVER_PROTOCOL = "app-server-jsonl-v2"
DEFAULT_STARTUP_TIMEOUT_SECONDS = 5.0
DEFAULT_TURN_TIMEOUT_SECONDS = 120.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_FRAME_BYTES = 256 * 1024
DEFAULT_MAX_STDOUT_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_STDERR_BYTES = 64 * 1024

_SAFE_ENVIRONMENT = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TZ",
        "USER",
    }
)
_VERSION = re.compile(r"(?<![A-Za-z0-9])v?(\d+(?:\.\d+){1,3}(?:-[A-Za-z0-9.]+)?)")


class CodexRuntimeError(RuntimeError):
    """Sanitized base error for the Codex process/protocol boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CodexRuntimeConfigurationError(CodexRuntimeError):
    pass


class CodexRuntimeNotFoundError(CodexRuntimeError):
    pass


class CodexRuntimeTimeoutError(CodexRuntimeError):
    pass


class CodexRuntimeProcessError(CodexRuntimeError):
    pass


class CodexProtocolError(CodexRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CodexRuntimeSettings:
    """External runtime selection and server-enforced transport limits."""

    executable: Path | None
    codex_home: Path | None = None
    model: str | None = None
    isolated_cwd: Path | None = None
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS
    turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS
    shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS
    max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES
    experimental_api: bool = False

    def __post_init__(self) -> None:
        for path in (self.executable, self.codex_home, self.isolated_cwd):
            if path is not None and not path.is_absolute():
                raise CodexRuntimeConfigurationError("codex_path_must_be_absolute")
        if self.model is not None and (
            not self.model.strip()
            or self.model != self.model.strip()
            or len(self.model) > 128
            or any(character in self.model for character in "\r\n\0")
        ):
            raise CodexRuntimeConfigurationError("codex_model_invalid")
        if not 0 < self.startup_timeout_seconds <= 60:
            raise CodexRuntimeConfigurationError("codex_startup_timeout_invalid")
        if not 0 < self.turn_timeout_seconds <= 1800:
            raise CodexRuntimeConfigurationError("codex_turn_timeout_invalid")
        if not 0 < self.shutdown_timeout_seconds <= 30:
            raise CodexRuntimeConfigurationError("codex_shutdown_timeout_invalid")
        if not 1024 <= self.max_frame_bytes <= 2 * 1024 * 1024:
            raise CodexRuntimeConfigurationError("codex_frame_limit_invalid")
        if not self.max_frame_bytes <= self.max_stdout_bytes <= 32 * 1024 * 1024:
            raise CodexRuntimeConfigurationError("codex_stdout_limit_invalid")
        if not 1024 <= self.max_stderr_bytes <= 1024 * 1024:
            raise CodexRuntimeConfigurationError("codex_stderr_limit_invalid")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> CodexRuntimeSettings:
        source = os.environ if environ is None else environ
        executable = _optional_path(source.get(CODEX_EXECUTABLE_ENV))
        codex_home = _optional_path(source.get(CODEX_HOME_OVERRIDE_ENV))
        isolated_cwd = _optional_path(source.get(CODEX_ISOLATED_CWD_ENV))
        model = source.get(CODEX_MODEL_ENV) or None
        return cls(
            executable=executable,
            codex_home=codex_home,
            model=model,
            isolated_cwd=isolated_cwd,
            startup_timeout_seconds=_float_setting(
                source,
                CODEX_STARTUP_TIMEOUT_ENV,
                DEFAULT_STARTUP_TIMEOUT_SECONDS,
            ),
            turn_timeout_seconds=_float_setting(
                source,
                CODEX_TURN_TIMEOUT_ENV,
                DEFAULT_TURN_TIMEOUT_SECONDS,
            ),
            experimental_api=_bool_setting(source, CODEX_EXPERIMENTAL_API_ENV, False),
        )


@dataclass(frozen=True, slots=True)
class CodexThreadPolicy:
    """Host-owned isolation parameters for one future ephemeral product thread."""

    cwd: Path
    model: str | None
    ephemeral: bool = True
    approval_policy: str = "never"
    sandbox: str = "read-only"

    def start_params(self) -> dict[str, object]:
        params: dict[str, object] = {
            "approvalPolicy": self.approval_policy,
            "cwd": str(self.cwd),
            "dynamicTools": [],
            "environments": [],
            "ephemeral": self.ephemeral,
            "runtimeWorkspaceRoots": [],
            "sandbox": self.sandbox,
        }
        if self.model is not None:
            params["model"] = self.model
        return params


@dataclass(frozen=True, slots=True)
class CodexServerInfo:
    user_agent: str
    platform_family: str
    platform_os: str


class CodexProbeState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    NOT_FOUND = "not_found"
    HANDSHAKE_FAILED = "handshake_failed"
    COMPATIBLE = "compatible"


@dataclass(frozen=True, slots=True)
class CodexRuntimeProbe:
    """Sanitized compatibility result; auth/model usability remain explicit unknowns."""

    state: CodexProbeState
    protocol: str | None = None
    runtime_version: str | None = None
    auth_state: str = "unknown"
    model_state: str = "unknown"
    error_code: str | None = None


class CodexAppServerClient:
    """Small sequential JSONL client for one bounded App Server subprocess."""

    def __init__(
        self,
        *,
        settings: CodexRuntimeSettings,
        process: asyncio.subprocess.Process,
        cwd: Path,
        temporary_cwd: tempfile.TemporaryDirectory[str] | None,
    ) -> None:
        self._settings = settings
        self._process = process
        self._cwd = cwd
        self._temporary_cwd = temporary_cwd
        self._next_request_id = 1
        self._stdout_bytes = 0
        self._stderr_tail = bytearray()
        self._stderr_bytes = 0
        self._request_lock = asyncio.Lock()
        self._notifications: deque[dict[str, object]] = deque()
        self._stderr_task = asyncio.create_task(self._capture_stderr())
        self._closed = False
        self.server_info: CodexServerInfo | None = None

    @classmethod
    async def start(cls, settings: CodexRuntimeSettings) -> CodexAppServerClient:
        executable = _resolved_executable(settings.executable)
        temporary_cwd: tempfile.TemporaryDirectory[str] | None = None
        if settings.isolated_cwd is None:
            temporary_cwd = tempfile.TemporaryDirectory(prefix="odoo-ai-codex-")
            cwd = Path(temporary_cwd.name).resolve()
        else:
            cwd = settings.isolated_cwd.resolve()
            if not cwd.is_dir():
                raise CodexRuntimeConfigurationError("codex_isolated_cwd_invalid")
        argv = (
            str(executable),
            "app-server",
            "--stdio",
            "--strict-config",
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=_codex_environment(settings),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=settings.max_frame_bytes + 1,
                start_new_session=os.name == "posix",
            )
        except FileNotFoundError:
            if temporary_cwd is not None:
                temporary_cwd.cleanup()
            raise CodexRuntimeNotFoundError("codex_runtime_not_found") from None
        except (OSError, PermissionError):
            if temporary_cwd is not None:
                temporary_cwd.cleanup()
            raise CodexRuntimeProcessError("codex_runtime_start_failed") from None
        client = cls(
            settings=settings,
            process=process,
            cwd=cwd,
            temporary_cwd=temporary_cwd,
        )
        try:
            await client._initialize()
        except BaseException:
            await client.close()
            raise
        return client

    @property
    def thread_policy(self) -> CodexThreadPolicy:
        return CodexThreadPolicy(cwd=self._cwd, model=self._settings.model)

    @property
    def stderr_metadata(self) -> dict[str, int | bool]:
        return {
            "captured_bytes": len(self._stderr_tail),
            "total_bytes": self._stderr_bytes,
            "truncated": self._stderr_bytes > len(self._stderr_tail),
        }

    async def request(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        if self._closed:
            raise CodexRuntimeProcessError("codex_runtime_closed")
        timeout = timeout_seconds or self._settings.turn_timeout_seconds
        async with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            await self._send(
                {"id": request_id, "method": method, "params": dict(params)},
                timeout=timeout,
            )
            while True:
                message = await self._read(timeout=timeout)
                if "id" in message:
                    if message.get("id") != request_id:
                        raise CodexProtocolError("codex_response_id_mismatch")
                    if "error" in message:
                        raise CodexProtocolError("codex_provider_error")
                    if "result" not in message:
                        raise CodexProtocolError("codex_response_malformed")
                    return message["result"]
                if isinstance(message.get("method"), str):
                    self._notifications.append(message)
                    continue
                raise CodexProtocolError("codex_message_malformed")

    async def notify(self, method: str, params: Mapping[str, object] | None = None) -> None:
        message: dict[str, object] = {"method": method}
        if params is not None:
            message["params"] = dict(params)
        await self._send(message, timeout=self._settings.startup_timeout_seconds)

    async def next_notification(self, *, timeout_seconds: float | None = None) -> dict[str, object]:
        if self._notifications:
            return self._notifications.popleft()
        timeout = timeout_seconds or self._settings.turn_timeout_seconds
        message = await self._read(timeout=timeout)
        if "id" in message:
            raise CodexProtocolError("codex_unexpected_response")
        if not isinstance(message.get("method"), str):
            raise CodexProtocolError("codex_message_malformed")
        return message

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stdin = self._process.stdin
        if stdin is not None:
            stdin.close()
            try:
                await stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        try:
            await asyncio.wait_for(
                self._process.wait(),
                timeout=self._settings.shutdown_timeout_seconds,
            )
        except TimeoutError:
            self._terminate(signal.SIGTERM)
            try:
                await asyncio.wait_for(
                    self._process.wait(),
                    timeout=self._settings.shutdown_timeout_seconds,
                )
            except TimeoutError:
                self._terminate(signal.SIGKILL)
                await self._process.wait()
        try:
            await asyncio.wait_for(self._stderr_task, timeout=1)
        except TimeoutError:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
        if self._temporary_cwd is not None:
            self._temporary_cwd.cleanup()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        await self.close()

    async def _initialize(self) -> None:
        result = await self.request(
            "initialize",
            {
                "capabilities": {
                    "experimentalApi": self._settings.experimental_api,
                    "optOutNotificationMethods": [],
                },
                "clientInfo": {
                    "name": "odoo-ai-assistant",
                    "title": "Odoo AI Assistant",
                    "version": "0.1.0",
                },
            },
            timeout_seconds=self._settings.startup_timeout_seconds,
        )
        if not isinstance(result, dict):
            raise CodexProtocolError("codex_initialize_response_invalid")
        required = ("platformFamily", "platformOs", "userAgent")
        if any(not isinstance(result.get(name), str) for name in required):
            raise CodexProtocolError("codex_initialize_response_invalid")
        self.server_info = CodexServerInfo(
            user_agent=cast(str, result["userAgent"])[:256],
            platform_family=cast(str, result["platformFamily"])[:32],
            platform_os=cast(str, result["platformOs"])[:32],
        )
        await self.notify("initialized")

    async def _send(self, message: Mapping[str, object], *, timeout: float) -> None:
        stdin = self._process.stdin
        if stdin is None or self._process.returncode is not None:
            raise CodexRuntimeProcessError("codex_process_not_running")
        try:
            payload = (
                json.dumps(
                    dict(message),
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            )
        except (TypeError, ValueError):
            raise CodexProtocolError("codex_request_not_serializable") from None
        if len(payload) > self._settings.max_frame_bytes:
            raise CodexProtocolError("codex_request_frame_too_large")
        try:
            stdin.write(payload)
            await asyncio.wait_for(stdin.drain(), timeout=timeout)
        except TimeoutError:
            raise CodexRuntimeTimeoutError("codex_write_timeout") from None
        except (BrokenPipeError, ConnectionResetError):
            raise CodexRuntimeProcessError("codex_process_eof") from None

    async def _read(self, *, timeout: float) -> dict[str, object]:
        stdout = self._process.stdout
        if stdout is None:
            raise CodexRuntimeProcessError("codex_stdout_unavailable")
        try:
            raw = await asyncio.wait_for(stdout.readline(), timeout=timeout)
        except TimeoutError:
            raise CodexRuntimeTimeoutError("codex_read_timeout") from None
        except (ValueError, asyncio.LimitOverrunError):
            raise CodexProtocolError("codex_response_frame_too_large") from None
        if not raw:
            raise CodexRuntimeProcessError("codex_process_eof")
        self._stdout_bytes += len(raw)
        if len(raw) > self._settings.max_frame_bytes:
            raise CodexProtocolError("codex_response_frame_too_large")
        if self._stdout_bytes > self._settings.max_stdout_bytes:
            raise CodexProtocolError("codex_stdout_budget_exceeded")
        try:
            message = json.loads(raw)
        except (UnicodeError, ValueError):
            raise CodexProtocolError("codex_response_malformed") from None
        if not isinstance(message, dict):
            raise CodexProtocolError("codex_response_malformed")
        return cast(dict[str, object], message)

    async def _capture_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        while chunk := await stderr.read(4096):
            self._stderr_bytes += len(chunk)
            self._stderr_tail.extend(chunk)
            overflow = len(self._stderr_tail) - self._settings.max_stderr_bytes
            if overflow > 0:
                del self._stderr_tail[:overflow]

    def _terminate(self, requested_signal: signal.Signals) -> None:
        if self._process.returncode is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(self._process.pid, requested_signal)
            elif requested_signal is signal.SIGKILL:
                self._process.kill()
            else:
                self._process.terminate()
        except ProcessLookupError:
            return


async def probe_codex_runtime(settings: CodexRuntimeSettings) -> CodexRuntimeProbe:
    if settings.executable is None:
        return CodexRuntimeProbe(state=CodexProbeState.NOT_CONFIGURED)
    try:
        client = await CodexAppServerClient.start(settings)
    except CodexRuntimeNotFoundError as error:
        return CodexRuntimeProbe(state=CodexProbeState.NOT_FOUND, error_code=error.code)
    except CodexRuntimeError as error:
        return CodexRuntimeProbe(
            state=CodexProbeState.HANDSHAKE_FAILED,
            error_code=error.code,
        )
    try:
        info = client.server_info
        version_match = _VERSION.search(info.user_agent) if info is not None else None
        return CodexRuntimeProbe(
            state=CodexProbeState.COMPATIBLE,
            protocol=APP_SERVER_PROTOCOL,
            runtime_version=version_match.group(1) if version_match else None,
        )
    finally:
        await client.close()


def _resolved_executable(executable: Path | None) -> Path:
    if executable is None:
        raise CodexRuntimeConfigurationError("codex_runtime_not_configured")
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        raise CodexRuntimeNotFoundError("codex_runtime_not_found") from None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise CodexRuntimeNotFoundError("codex_runtime_not_found")
    return resolved


def _codex_environment(settings: CodexRuntimeSettings) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in _SAFE_ENVIRONMENT or name.startswith("LC_")
    }
    if settings.codex_home is not None:
        environment["CODEX_HOME"] = str(settings.codex_home.resolve())
    else:
        environment.pop("CODEX_HOME", None)
    return environment


def _optional_path(raw: str | None) -> Path | None:
    if raw is None or not raw.strip():
        return None
    if raw != raw.strip() or any(character in raw for character in "\r\n\0"):
        raise CodexRuntimeConfigurationError("codex_path_invalid")
    return Path(raw)


def _float_setting(source: Mapping[str, str], name: str, default: float) -> float:
    raw = source.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise CodexRuntimeConfigurationError("codex_timeout_invalid") from None
    return value


def _bool_setting(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise CodexRuntimeConfigurationError("codex_boolean_setting_invalid")
