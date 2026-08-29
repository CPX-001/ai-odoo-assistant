"""Installation-scoped Codex account gate for the embedded Assistant."""

from __future__ import annotations

from ..runtime import (
    CodexAccountError,
    CodexAccountManager,
    CodexAccountStatus,
    RuntimePathError,
    RuntimePaths,
    detect_codex,
)

_EXECUTABLE_PARAMETER = "odoo_ai_assistant.codex_executable"
_ACCOUNT_STATES = frozenset(
    {
        "authenticated",
        "authentication_error",
        "login_pending",
        "not_authenticated",
    }
)


class RuntimeAccountGateError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def runtime_status_payload(env) -> dict[str, object]:
    status, can_configure = _effective_status(env, include_rate_limits=False)
    state = status.state
    return {
        "ok": True,
        "state": state,
        "requires_setup": state != "authenticated",
        "can_configure": can_configure,
    }


def runtime_account_payload(env, *, include_rate_limits: bool = True) -> dict[str, object]:
    status, can_configure = _effective_status(
        env,
        include_rate_limits=bool(include_rate_limits and env.user.has_group("base.group_system")),
    )
    account = None
    if can_configure and status.state == "authenticated":
        account = {
            "auth_mode": status.auth_mode,
            "email": status.email,
            "plan_type": status.plan_type,
            "rate_limits": [dict(row) for row in status.rate_limits],
        }
    return {
        "ok": True,
        "state": status.state,
        "requires_setup": status.state != "authenticated",
        "can_configure": can_configure,
        "account": account,
    }


def require_runtime_authenticated(env) -> None:
    try:
        manager = _runtime_manager(env)
    except RuntimeAccountGateError:
        raise
    try:
        status = manager.status(include_rate_limits=False)
    except CodexAccountError as error:
        raise RuntimeAccountGateError(_account_error_code(error)) from error
    if status.state == "authenticated":
        return
    if status.state == "authentication_error":
        raise RuntimeAccountGateError("authentication_failed")
    raise RuntimeAccountGateError("codex_not_connected")


def _effective_status(env, *, include_rate_limits: bool) -> tuple[CodexAccountStatus, bool]:
    can_configure = env.user.has_group("base.group_system")
    try:
        manager = _runtime_manager(env)
    except RuntimeAccountGateError as error:
        state = "codex_unavailable" if error.code == "codex_unavailable" else "authentication_error"
        return CodexAccountStatus(state=state, error_code=error.code), can_configure
    try:
        status = manager.status(include_rate_limits=include_rate_limits)
    except CodexAccountError as error:
        return (
            CodexAccountStatus(state="authentication_error", error_code=error.code),
            can_configure,
        )
    if status.state not in _ACCOUNT_STATES:
        return (
            CodexAccountStatus(
                state="authentication_error",
                error_code=status.error_code or "codex_account_unavailable",
            ),
            can_configure,
        )
    return status, can_configure


def _runtime_manager(env) -> CodexAccountManager:
    configured = env["ir.config_parameter"]._get_param(_EXECUTABLE_PARAMETER) or ""
    codex = detect_codex(configured)
    if not codex.ready or codex.executable is None:
        raise RuntimeAccountGateError("codex_unavailable")
    try:
        paths = RuntimePaths.from_odoo().ensure()
    except RuntimePathError as error:
        raise RuntimeAccountGateError("authentication_failed") from error
    return CodexAccountManager(executable=codex.executable, paths=paths)


def _account_error_code(error: CodexAccountError) -> str:
    if error.code in {
        "codex_runtime_not_found",
        "codex_runtime_start_failed",
        "codex_runtime_storage_unavailable",
    }:
        return "codex_unavailable"
    return "authentication_failed"
