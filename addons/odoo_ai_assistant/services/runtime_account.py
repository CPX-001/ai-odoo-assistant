"""Database-scoped Codex account gate for the embedded Assistant."""

from __future__ import annotations

from odoo.exceptions import AccessError

from ..runtime import (
    CodexAccountError,
    CodexAccountManager,
    CodexAccountStatus,
    RuntimePathError,
    RuntimePaths,
    detect_codex,
)

_CONNECTION_PARAMETER = "odoo_ai_assistant.codex_connection_enabled"
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


def database_connection_enabled(env) -> bool:
    value = env["ir.config_parameter"]._get_param(_CONNECTION_PARAMETER)
    # Fresh installs write an explicit false value from post_init_hook. An absent
    # value means a pre-ADR-018 database and preserves its existing Codex session
    # across module upgrade instead of forcing an unexpected reconnect.
    if value is None or value is False:
        return True
    return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"}


def enable_database_connection(env) -> None:
    _require_admin(env)
    env["ir.config_parameter"].set_param(_CONNECTION_PARAMETER, "true")


def disable_database_connection(env) -> None:
    _require_admin(env)
    env["ir.config_parameter"].set_param(_CONNECTION_PARAMETER, "false")


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
    login = None
    if can_configure and status.state == "authenticated":
        account = {
            "auth_mode": status.auth_mode,
            "email": status.email,
            "plan_type": status.plan_type,
            "rate_limits": [dict(row) for row in status.rate_limits],
        }
    elif can_configure and status.state == "login_pending":
        login = {
            "verification_url": status.verification_url,
            "user_code": status.user_code,
        }
    return {
        "ok": True,
        "state": status.state,
        "requires_setup": status.state != "authenticated",
        "can_configure": can_configure,
        "account": account,
        "login": login,
    }


def connect_database(env) -> dict[str, object]:
    _require_admin(env)
    manager = _runtime_manager(env)
    enable_database_connection(env)
    try:
        manager.start_login()
    except CodexAccountError as error:
        disable_database_connection(env)
        raise RuntimeAccountGateError(_account_error_code(error)) from error
    return runtime_account_payload(env)


def cancel_database_login(env) -> dict[str, object]:
    _require_admin(env)
    manager = _runtime_manager(env)
    try:
        manager.cancel_login()
    except CodexAccountError as error:
        raise RuntimeAccountGateError(_account_error_code(error)) from error
    disable_database_connection(env)
    return runtime_account_payload(env)


def logout_database(env) -> dict[str, object]:
    _require_admin(env)
    manager = _runtime_manager(env)
    try:
        manager.logout()
    except CodexAccountError as error:
        raise RuntimeAccountGateError(_account_error_code(error)) from error
    disable_database_connection(env)
    return runtime_account_payload(env)


def require_runtime_authenticated(env) -> None:
    if not database_connection_enabled(env):
        raise RuntimeAccountGateError("codex_not_connected")
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
    if not database_connection_enabled(env):
        return CodexAccountStatus(state="not_authenticated"), can_configure
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


def _require_admin(env) -> None:
    if not env.user.has_group("base.group_system"):
        raise AccessError("Assistant account management requires Settings access")
