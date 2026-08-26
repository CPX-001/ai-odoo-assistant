"""Installation-scoped Codex/ChatGPT account lifecycle for the embedded runtime."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .paths import RuntimePaths

_FRAME: Final = 256 * 1024
_STDOUT: Final = 2 * 1024 * 1024
_STDERR: Final = 64 * 1024
_STATE: Final = 64 * 1024
_SAFE_ENV: Final = frozenset(
    {"HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE", "TZ", "USER"}
)
_SAFE_CODE = re.compile(r"^[a-z0-9_]{1,128}$")
_SAFE_USER_CODE = re.compile(r"^[A-Za-z0-9-]{4,64}$")
_SAFE_PLAN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_SAFE_LIMIT = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")
_ACTIVE = frozenset({"starting", "pending"})
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timed_out"})


class CodexAccountError(RuntimeError):
    def __init__(self, code: str) -> None:
        normalized = code if isinstance(code, str) and _SAFE_CODE.fullmatch(code) else "codex_account_error"
        super().__init__(normalized)
        self.code = normalized


@dataclass(frozen=True, slots=True)
class CodexAccountStatus:
    state: str
    auth_mode: str | None = None
    email: str | None = None
    plan_type: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    error_code: str | None = None
    rate_limits: tuple[dict[str, object], ...] = ()

    @property
    def connected(self) -> bool:
        return self.state == "authenticated"

    @property
    def login_pending(self) -> bool:
        return self.state == "login_pending"

    def browser_payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "connected": self.connected,
            "login_pending": self.login_pending,
            "auth_mode": self.auth_mode,
            "email": self.email,
            "plan_type": self.plan_type,
            "verification_url": self.verification_url,
            "user_code": self.user_code,
            "error_code": self.error_code,
            "rate_limits": [dict(row) for row in self.rate_limits],
        }


class CodexAccountManager:
    """Manage one global account while Codex remains owner of credential material."""

    def __init__(
        self,
        *,
        executable: Path,
        paths: RuntimePaths,
        startup_timeout_seconds: float = 8.0,
        request_timeout_seconds: float = 8.0,
        shutdown_timeout_seconds: float = 2.0,
        login_timeout_seconds: int = 900,
    ) -> None:
        self.executable = _executable(executable)
        self.paths = paths.ensure()
        self.startup_timeout_seconds = _timeout(startup_timeout_seconds, 1, 60)
        self.request_timeout_seconds = _timeout(request_timeout_seconds, 1, 60)
        self.shutdown_timeout_seconds = _timeout(shutdown_timeout_seconds, 0.5, 30)
        if type(login_timeout_seconds) is not int or not 60 <= login_timeout_seconds <= 3600:
            raise CodexAccountError("codex_login_timeout_invalid")
        self.login_timeout_seconds = login_timeout_seconds
        self.auth_runtime = self.paths.runtime / "codex_auth"
        _private_dir(self.auth_runtime)
        self.state_path = self.auth_runtime / "login-state.json"
        self.cancel_path = self.auth_runtime / "login.cancel"
        self.lock_path = self.auth_runtime / "login.lock"

    def status(self, *, include_rate_limits: bool = False) -> CodexAccountStatus:
        state = _read_state(self.state_path)
        if state and state.get("state") in _ACTIVE:
            if _lock_held(self.lock_path):
                return _pending(state)
            state = _interrupt(self.state_path, state)
        current = self._runtime_status(include_rate_limits=include_rate_limits)
        if current.state != "not_authenticated":
            return current
        if state and state.get("state") in {"failed", "timed_out"}:
            code = state.get("error_code")
            if isinstance(code, str) and _SAFE_CODE.fullmatch(code):
                return CodexAccountStatus(state="authentication_error", error_code=code)
        return current

    def _runtime_status(self, *, include_rate_limits: bool) -> CodexAccountStatus:
        try:
            payload = asyncio.run(self._request("account/read", {"refreshToken": False}))
            account = _account(payload)
        except CodexAccountError as error:
            return CodexAccountStatus(state="authentication_error", error_code=error.code)
        if account is None:
            return CodexAccountStatus(state="not_authenticated")
        limits: tuple[dict[str, object], ...] = ()
        if include_rate_limits:
            try:
                limits = _limits(asyncio.run(self._request("account/rateLimits/read", {})))
            except CodexAccountError:
                pass
        return CodexAccountStatus(
            state="authenticated",
            auth_mode=account["auth_mode"],
            email=account["email"],
            plan_type=account["plan_type"],
            rate_limits=limits,
        )

    async def _request(self, method: str, params: dict[str, object]):
        client = await _Client.start(
            self.executable,
            self.paths.codex_home,
            startup=self.startup_timeout_seconds,
            request=self.request_timeout_seconds,
            shutdown=self.shutdown_timeout_seconds,
        )
        async with client:
            return await client.request(method, params)

    def start_login(self) -> CodexAccountStatus:
        lock_fd = _open_lock(self.lock_path)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                state = _read_state(self.state_path)
                if state and state.get("state") in _ACTIVE:
                    return _pending(state)
                raise CodexAccountError("codex_login_busy") from None
            current = self._runtime_status(include_rate_limits=False)
            if current.connected:
                return current
            if current.error_code == "codex_account_api_unsupported":
                raise CodexAccountError(current.error_code)
            _unlink(self.cancel_path)
            attempt = uuid.uuid4().hex
            now = int(time.time())
            _write_state(self.state_path, _state(attempt, "starting", now, now + self.login_timeout_seconds))
            worker = Path(__file__).with_name("account_worker.py").resolve(strict=True)
            os.set_inheritable(lock_fd, True)
            argv = [
                sys.executable,
                str(worker),
                "--executable", str(self.executable),
                "--codex-home", str(self.paths.codex_home),
                "--state-path", str(self.state_path),
                "--cancel-path", str(self.cancel_path),
                "--attempt-id", attempt,
                "--lock-fd", str(lock_fd),
                "--login-timeout-seconds", str(self.login_timeout_seconds),
                "--startup-timeout-seconds", str(self.startup_timeout_seconds),
                "--request-timeout-seconds", str(self.request_timeout_seconds),
                "--shutdown-timeout-seconds", str(self.shutdown_timeout_seconds),
            ]
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=str(self.auth_runtime),
                    env=_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    pass_fds=(lock_fd,),
                    start_new_session=True,
                )
            except (OSError, ValueError):
                _terminal(self.state_path, attempt, "failed", "codex_login_worker_start_failed")
                raise CodexAccountError("codex_login_worker_start_failed") from None
        finally:
            os.close(lock_fd)

        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            state = _read_state(self.state_path)
            if state and state.get("attempt_id") == attempt:
                if state.get("state") == "pending":
                    return _pending(state)
                if state.get("state") == "succeeded":
                    return self.status()
                if state.get("state") in _TERMINAL:
                    code = state.get("error_code")
                    raise CodexAccountError(code if isinstance(code, str) else "codex_login_start_failed")
            if process.poll() is not None:
                state = _read_state(self.state_path)
                if state and state.get("attempt_id") == attempt and state.get("state") in _ACTIVE:
                    _terminal(self.state_path, attempt, "failed", "codex_login_worker_failed")
                raise CodexAccountError("codex_login_worker_failed")
            time.sleep(0.05)
        state = _read_state(self.state_path)
        if state and state.get("attempt_id") == attempt and state.get("state") in _ACTIVE and _lock_held(self.lock_path):
            return _pending(state)
        raise CodexAccountError("codex_login_start_timeout")

    def cancel_login(self) -> CodexAccountStatus:
        state = _read_state(self.state_path)
        if not state or state.get("state") not in _ACTIVE:
            return self.status()
        if not _lock_held(self.lock_path):
            _interrupt(self.state_path, state)
            return self.status()
        _touch(self.cancel_path)
        deadline = time.monotonic() + min(3.0, self.request_timeout_seconds)
        while time.monotonic() < deadline:
            state = _read_state(self.state_path)
            if not state or state.get("state") not in _ACTIVE:
                break
            time.sleep(0.05)
        return self.status()

    def logout(self) -> CodexAccountStatus:
        if _lock_held(self.lock_path):
            raise CodexAccountError("codex_login_pending")
        result = asyncio.run(self._request("account/logout", {}))
        if not isinstance(result, dict):
            raise CodexAccountError("codex_logout_response_invalid")
        _unlink(self.cancel_path)
        _unlink(self.state_path)
        return self.status()


class _Client:
    def __init__(self, process, cwd, request: float, shutdown: float) -> None:
        self.process = process
        self.cwd = cwd
        self.request_timeout = request
        self.shutdown_timeout = shutdown
        self.next_id = 1
        self.stdout_bytes = 0
        self.stderr_tail = bytearray()
        self.events: deque[dict[str, object]] = deque()
        self.stderr_task = asyncio.create_task(self._stderr())
        self.closed = False

    @classmethod
    async def start(cls, executable: Path, home: Path, *, startup: float, request: float, shutdown: float):
        executable = _executable(executable)
        home = _home(home)
        cwd = tempfile.TemporaryDirectory(prefix="odoo-ai-codex-auth-")
        argv = (
            str(executable), "app-server", "--stdio", "--strict-config",
            "--config", "mcp_servers={}",
            "--config", 'cli_auth_credentials_store="file"',
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd.name,
                env=_codex_environment(home),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_FRAME + 1,
                start_new_session=os.name == "posix",
            )
        except (FileNotFoundError, PermissionError, OSError):
            cwd.cleanup()
            raise CodexAccountError("codex_runtime_start_failed") from None
        client = cls(process, cwd, request, shutdown)
        try:
            result = await client.request(
                "initialize",
                {
                    "capabilities": {"experimentalApi": True, "optOutNotificationMethods": []},
                    "clientInfo": {"name": "odoo-ai-assistant-auth", "title": "Odoo AI Assistant", "version": "embedded-auth-1"},
                },
                timeout=startup,
            )
            if not isinstance(result, dict) or any(not isinstance(result.get(key), str) for key in ("platformFamily", "platformOs", "userAgent")):
                raise CodexAccountError("codex_initialize_response_invalid")
            await client.notify("initialized", timeout=startup)
            return client
        except BaseException:
            await client.close()
            raise

    async def request(self, method: str, params: dict[str, object], *, timeout: float | None = None):
        request_id = self.next_id
        self.next_id += 1
        limit = self.request_timeout if timeout is None else timeout
        await self._send({"id": request_id, "method": method, "params": params}, limit)
        while True:
            message = await self._read(limit)
            if isinstance(message.get("method"), str):
                self.events.append(message)
                continue
            if message.get("id") != request_id:
                raise CodexAccountError("codex_response_id_mismatch")
            if "error" in message:
                error = message.get("error")
                code = "codex_account_api_unsupported" if isinstance(error, dict) and error.get("code") == -32601 else "codex_provider_error"
                raise CodexAccountError(code)
            if "result" not in message:
                raise CodexAccountError("codex_response_malformed")
            return message["result"]

    async def notify(self, method: str, *, timeout: float) -> None:
        await self._send({"method": method}, timeout)

    async def event(self, *, timeout: float) -> dict[str, object]:
        return self.events.popleft() if self.events else await self._read(timeout)

    async def _send(self, value: dict[str, object], timeout: float) -> None:
        stdin = self.process.stdin
        if stdin is None or self.process.returncode is not None:
            raise CodexAccountError("codex_process_not_running")
        try:
            raw = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        except (TypeError, ValueError):
            raise CodexAccountError("codex_request_not_serializable") from None
        if len(raw) > _FRAME:
            raise CodexAccountError("codex_request_frame_too_large")
        try:
            stdin.write(raw)
            await asyncio.wait_for(stdin.drain(), timeout)
        except TimeoutError:
            raise CodexAccountError("codex_write_timeout") from None
        except (BrokenPipeError, ConnectionResetError):
            raise CodexAccountError("codex_process_eof") from None

    async def _read(self, timeout: float) -> dict[str, object]:
        stdout = self.process.stdout
        if stdout is None:
            raise CodexAccountError("codex_stdout_unavailable")
        try:
            raw = await asyncio.wait_for(stdout.readline(), timeout)
        except TimeoutError:
            raise CodexAccountError("codex_read_timeout") from None
        except (ValueError, asyncio.LimitOverrunError):
            raise CodexAccountError("codex_response_frame_too_large") from None
        if not raw:
            raise CodexAccountError("codex_process_eof")
        self.stdout_bytes += len(raw)
        if len(raw) > _FRAME or self.stdout_bytes > _STDOUT:
            raise CodexAccountError("codex_stdout_budget_exceeded")
        try:
            value = json.loads(raw)
        except (UnicodeError, ValueError):
            raise CodexAccountError("codex_response_malformed") from None
        if not isinstance(value, dict):
            raise CodexAccountError("codex_response_malformed")
        return cast(dict[str, object], value)

    async def _stderr(self) -> None:
        if self.process.stderr is None:
            return
        while chunk := await self.process.stderr.read(4096):
            self.stderr_tail.extend(chunk)
            if len(self.stderr_tail) > _STDERR:
                del self.stderr_tail[:-_STDERR]

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process.stdin is not None:
            self.process.stdin.close()
            try:
                await self.process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        try:
            await asyncio.wait_for(self.process.wait(), self.shutdown_timeout)
        except TimeoutError:
            self._kill(signal.SIGTERM)
            try:
                await asyncio.wait_for(self.process.wait(), self.shutdown_timeout)
            except TimeoutError:
                self._kill(signal.SIGKILL)
                await self.process.wait()
        try:
            await asyncio.wait_for(self.stderr_task, 1.0)
        except TimeoutError:
            self.stderr_task.cancel()
            await asyncio.gather(self.stderr_task, return_exceptions=True)
        self.cwd.cleanup()

    def _kill(self, sig) -> None:
        if self.process.returncode is not None:
            return
        try:
            os.killpg(self.process.pid, sig) if os.name == "posix" else self.process.kill()
        except ProcessLookupError:
            pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        await self.close()


async def run_device_login_worker(
    *,
    executable: Path,
    codex_home: Path,
    state_path: Path,
    cancel_path: Path,
    attempt_id: str,
    login_timeout_seconds: int,
    startup_timeout_seconds: float,
    request_timeout_seconds: float,
    shutdown_timeout_seconds: float,
) -> None:
    _worker_paths(codex_home, state_path, cancel_path)
    client = None
    try:
        client = await _Client.start(
            executable,
            codex_home,
            startup=startup_timeout_seconds,
            request=request_timeout_seconds,
            shutdown=shutdown_timeout_seconds,
        )
        result = await client.request("account/login/start", {"type": "chatgptDeviceCode"})
        login_id, url, code = _device(result)
        now = int(time.time())
        previous = _read_state(state_path) or {}
        created = previous.get("created_at") if previous.get("attempt_id") == attempt_id else now
        _write_state(
            state_path,
            _state(
                attempt_id,
                "pending",
                created if type(created) is int else now,
                now + login_timeout_seconds,
                pid=os.getpid(),
                login_id=login_id,
                verification_url=url,
                user_code=code,
            ),
        )
        deadline = time.monotonic() + login_timeout_seconds
        while time.monotonic() < deadline:
            if cancel_path.exists():
                try:
                    _cancel(await client.request("account/login/cancel", {"loginId": login_id}))
                except CodexAccountError:
                    pass
                _terminal(state_path, attempt_id, "cancelled", None)
                return
            try:
                event = await client.event(timeout=min(1.0, request_timeout_seconds))
            except CodexAccountError as error:
                if error.code == "codex_read_timeout":
                    continue
                raise
            if event.get("method") != "account/login/completed":
                continue
            params = event.get("params")
            if not isinstance(params, dict) or params.get("loginId") != login_id or type(params.get("success")) is not bool:
                raise CodexAccountError("codex_login_completion_invalid")
            if not params["success"]:
                _terminal(state_path, attempt_id, "failed", "codex_login_failed")
                return
            if _account(await client.request("account/read", {"refreshToken": False})) is None:
                raise CodexAccountError("codex_login_completed_without_account")
            _harden_auth(codex_home)
            _terminal(state_path, attempt_id, "succeeded", None)
            return
        try:
            await client.request("account/login/cancel", {"loginId": login_id}, timeout=min(3.0, request_timeout_seconds))
        except CodexAccountError:
            pass
        _terminal(state_path, attempt_id, "timed_out", "codex_login_timeout")
    except CodexAccountError as error:
        _terminal(state_path, attempt_id, "failed", error.code)
    except (OSError, RuntimeError, TypeError, ValueError):
        _terminal(state_path, attempt_id, "failed", "codex_login_worker_failed")
    finally:
        if client is not None:
            await client.close()
        _unlink(cancel_path)


def _account(payload) -> dict[str, str | None] | None:
    if not isinstance(payload, dict) or type(payload.get("requiresOpenaiAuth")) is not bool:
        raise CodexAccountError("codex_account_response_invalid")
    value = payload.get("account")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CodexAccountError("codex_account_response_invalid")
    kind = value.get("type")
    if kind == "chatgpt":
        email, plan = value.get("email"), value.get("planType")
        if email is not None and (not isinstance(email, str) or not 3 <= len(email) <= 320):
            raise CodexAccountError("codex_account_response_invalid")
        if not isinstance(plan, str) or not _SAFE_PLAN.fullmatch(plan):
            raise CodexAccountError("codex_account_response_invalid")
        return {"auth_mode": "chatgpt", "email": email, "plan_type": plan}
    if kind in {"apiKey", "amazonBedrock"}:
        return {"auth_mode": "api_key" if kind == "apiKey" else "amazon_bedrock", "email": None, "plan_type": None}
    raise CodexAccountError("codex_account_response_invalid")


def _device(payload) -> tuple[str, str, str]:
    if not isinstance(payload, dict) or payload.get("type") != "chatgptDeviceCode":
        raise CodexAccountError("codex_login_response_invalid")
    login_id, url, code = payload.get("loginId"), payload.get("verificationUrl"), payload.get("userCode")
    if not isinstance(login_id, str) or not 1 <= len(login_id) <= 256:
        raise CodexAccountError("codex_login_response_invalid")
    if not isinstance(url, str) or not _safe_url(url):
        raise CodexAccountError("codex_login_response_invalid")
    if not isinstance(code, str) or not _SAFE_USER_CODE.fullmatch(code):
        raise CodexAccountError("codex_login_response_invalid")
    return login_id, url, code


def _cancel(payload) -> None:
    if not isinstance(payload, dict) or payload.get("status") not in {"canceled", "notFound"}:
        raise CodexAccountError("codex_login_cancel_response_invalid")


def _limits(payload) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict):
        raise CodexAccountError("codex_rate_limits_response_invalid")
    by_id = payload.get("rateLimitsByLimitId")
    if by_id is not None:
        if not isinstance(by_id, dict) or len(by_id) > 32:
            raise CodexAccountError("codex_rate_limits_response_invalid")
        snapshots = sorted(by_id.items())
    elif "rateLimits" in payload:
        snapshots = [(None, payload["rateLimits"])]
    else:
        raise CodexAccountError("codex_rate_limits_response_invalid")
    rows = []
    for fallback, snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise CodexAccountError("codex_rate_limits_response_invalid")
        limit_id = snapshot.get("limitId") or fallback
        name = snapshot.get("limitName")
        if limit_id is not None and (not isinstance(limit_id, str) or not _SAFE_LIMIT.fullmatch(limit_id)):
            raise CodexAccountError("codex_rate_limits_response_invalid")
        if name is not None and (not isinstance(name, str) or len(name) > 160):
            raise CodexAccountError("codex_rate_limits_response_invalid")
        for window_name in ("primary", "secondary"):
            window = snapshot.get(window_name)
            if window is None:
                continue
            if not isinstance(window, dict):
                raise CodexAccountError("codex_rate_limits_response_invalid")
            used, duration, resets = window.get("usedPercent"), window.get("windowDurationMins"), window.get("resetsAt")
            if type(used) is not int or not 0 <= used <= 100:
                raise CodexAccountError("codex_rate_limits_response_invalid")
            if duration is not None and (type(duration) is not int or duration <= 0):
                raise CodexAccountError("codex_rate_limits_response_invalid")
            if resets is not None and (type(resets) is not int or resets < 0):
                raise CodexAccountError("codex_rate_limits_response_invalid")
            rows.append({"limit_id": limit_id, "limit_name": name, "window": window_name, "used_percent": used, "window_duration_mins": duration, "resets_at": resets})
    return tuple(rows)


def _state(attempt, state, created, deadline, **extra) -> dict[str, object]:
    return {
        "schema_version": 1,
        "attempt_id": attempt,
        "state": state,
        "created_at": created,
        "updated_at": int(time.time()),
        "deadline_at": deadline,
        "pid": extra.get("pid"),
        "login_id": extra.get("login_id"),
        "verification_url": extra.get("verification_url"),
        "user_code": extra.get("user_code"),
        "error_code": extra.get("error_code"),
    }


def _pending(state) -> CodexAccountStatus:
    url, code = state.get("verification_url"), state.get("user_code")
    if state.get("state") == "pending" and (not isinstance(url, str) or not _safe_url(url) or not isinstance(code, str) or not _SAFE_USER_CODE.fullmatch(code)):
        return CodexAccountStatus(state="authentication_error", error_code="codex_login_state_invalid")
    return CodexAccountStatus(state="login_pending", verification_url=url if isinstance(url, str) else None, user_code=code if isinstance(code, str) else None)


def _terminal(path: Path, attempt: str, state: str, error: str | None) -> None:
    if state not in _TERMINAL:
        raise CodexAccountError("codex_login_state_invalid")
    old = _read_state(path) or {}
    if old.get("attempt_id") not in (None, attempt):
        return
    now = int(time.time())
    _write_state(path, _state(attempt, state, old.get("created_at") if type(old.get("created_at")) is int else now, old.get("deadline_at") if type(old.get("deadline_at")) is int else now, error_code=error))


def _interrupt(path: Path, state: dict[str, object]) -> dict[str, object]:
    attempt = state.get("attempt_id")
    if isinstance(attempt, str) and attempt:
        _terminal(path, attempt, "failed", "codex_login_interrupted")
    return _read_state(path) or state


def _read_state(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _STATE:
            raise CodexAccountError("codex_login_state_invalid")
        value = json.loads(path.read_text(encoding="utf-8"))
    except CodexAccountError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise CodexAccountError("codex_login_state_invalid") from None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise CodexAccountError("codex_login_state_invalid")
    return cast(dict[str, object], value)


def _write_state(path: Path, value: dict[str, object]) -> None:
    _private_dir(path.parent)
    if path.exists() and path.is_symlink():
        raise CodexAccountError("codex_login_state_invalid")
    try:
        raw = json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    except (TypeError, ValueError):
        raise CodexAccountError("codex_login_state_invalid") from None
    if len(raw) > _STATE:
        raise CodexAccountError("codex_login_state_invalid")
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        path.chmod(0o600)
    except OSError:
        _unlink(temp)
        raise CodexAccountError("codex_login_state_unavailable") from None


def _private_dir(path: Path) -> None:
    try:
        if path.is_symlink():
            raise CodexAccountError("codex_auth_path_invalid")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise CodexAccountError("codex_auth_path_invalid")
        path.chmod(0o700)
    except CodexAccountError:
        raise
    except OSError:
        raise CodexAccountError("codex_auth_path_unavailable") from None


def _open_lock(path: Path) -> int:
    _private_dir(path.parent)
    flags = os.O_RDWR | os.O_CREAT | (getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags, 0o600)
        os.fchmod(fd, 0o600)
        return fd
    except OSError:
        raise CodexAccountError("codex_login_lock_unavailable") from None


def _lock_held(path: Path) -> bool:
    fd = _open_lock(path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _touch(path: Path) -> None:
    _private_dir(path.parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        path.chmod(0o600)
    except OSError:
        raise CodexAccountError("codex_login_cancel_unavailable") from None


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _home(path: Path) -> Path:
    if path.is_symlink():
        raise CodexAccountError("codex_home_unavailable")
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_dir() or resolved.is_symlink():
            raise OSError
        resolved.chmod(0o700)
        return resolved
    except OSError:
        raise CodexAccountError("codex_home_unavailable") from None


def _worker_paths(home: Path, state: Path, cancel: Path) -> None:
    home = _home(home)
    runtime = state.parent.resolve(strict=True)
    if runtime != cancel.parent.resolve(strict=True) or not runtime.is_dir():
        raise CodexAccountError("codex_auth_path_invalid")
    try:
        runtime.relative_to(home.parent.resolve(strict=True) / "runtime")
    except ValueError:
        raise CodexAccountError("codex_auth_path_invalid") from None


def _harden_auth(home: Path) -> None:
    auth = home / "auth.json"
    try:
        if not auth.exists() or auth.is_symlink() or not auth.is_file():
            raise CodexAccountError("codex_auth_file_invalid")
        auth.chmod(0o600)
    except CodexAccountError:
        raise
    except OSError:
        raise CodexAccountError("codex_auth_file_invalid") from None


def _executable(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise CodexAccountError("codex_runtime_not_found") from None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise CodexAccountError("codex_runtime_not_found")
    return resolved


def _safe_url(value: str) -> bool:
    if len(value) > 2048:
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    trusted = host in {"openai.com", "chatgpt.com"} or host.endswith((".openai.com", ".chatgpt.com"))
    return parsed.scheme == "https" and trusted and parsed.username is None and parsed.password is None


def _environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in _SAFE_ENV or key.startswith("LC_")}


def _codex_environment(home: Path) -> dict[str, str]:
    environment = _environment()
    environment["CODEX_HOME"] = str(home.resolve(strict=True))
    return environment


def _timeout(value, minimum, maximum) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodexAccountError("codex_timeout_invalid")
    value = float(value)
    if not minimum <= value <= maximum:
        raise CodexAccountError("codex_timeout_invalid")
    return value


__all__ = ["CodexAccountError", "CodexAccountManager", "CodexAccountStatus", "run_device_login_worker"]
