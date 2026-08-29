"""Embedded Codex account diagnostics layered onto the existing admin surface."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from odoo import _, fields, models

from ..runtime import (
    CodexAccountError,
    CodexAccountManager,
    RuntimePathError,
    RuntimePaths,
    detect_codex,
)
from ..runtime.agent.auth_probe import isolated_account_usable
from ..runtime.agent.codex import CodexAgentError, CodexAgentSettings

_INCOMPATIBLE_ERRORS = frozenset(
    {
        "codex_account_api_unsupported",
        "codex_initialize_response_invalid",
    }
)
_UNUSABLE_ERRORS = frozenset(
    {
        "codex_auth_path_invalid",
        "codex_auth_path_unavailable",
        "codex_home_unavailable",
        "codex_runtime_not_found",
        "codex_runtime_start_failed",
    }
)


class AssistantDiagnosticsCodexAccount(models.TransientModel):
    _inherit = "odoo.ai.assistant.diagnostics"

    codex_account_state = fields.Char(readonly=True)
    codex_account_identity = fields.Char(readonly=True)
    codex_account_plan = fields.Char(readonly=True)
    codex_account_usage = fields.Text(readonly=True)
    codex_account_detail = fields.Char(readonly=True)

    def _diagnostic_values(self):
        values = super()._diagnostic_values()
        configured = (
            self.env["ir.config_parameter"]._get_param("odoo_ai_assistant.codex_executable")
            or ""
        )
        detected = detect_codex(configured)
        if not detected.ready or detected.executable is None:
            values.update(
                codex_account_state=_("Runtime unavailable"),
                codex_account_identity=False,
                codex_account_plan=False,
                codex_account_usage=False,
                codex_account_detail=_("Codex executable is missing or unusable."),
            )
            return values
        try:
            paths = RuntimePaths.from_odoo().ensure()
            manager = CodexAccountManager(
                executable=detected.executable,
                paths=paths,
            )
            status = manager.status(include_rate_limits=False)
        except RuntimePathError:
            values.update(
                codex_account_state=_("Runtime unusable"),
                codex_account_identity=False,
                codex_account_plan=False,
                codex_account_usage=False,
                codex_account_detail=_("The private Assistant runtime directory is unavailable."),
            )
            return values
        except CodexAccountError as error:
            values.update(
                codex_account_state=_account_error_state(error.code),
                codex_account_identity=False,
                codex_account_plan=False,
                codex_account_usage=False,
                codex_account_detail=_account_error_detail(error.code),
            )
            return values

        # Authentication/refresh belongs to the host's primary Codex lifecycle.
        # Diagnostics only validates the credential through the product-turn isolation
        # path and never mutates the provider-owned persistent HOME.
        if status.connected:
            status = manager.status(include_rate_limits=True)

        detail = {
            "not_authenticated": _("Codex is available but no account is connected."),
            "login_pending": _("A ChatGPT device login is currently pending."),
            "authentication_error": _(
                "The Codex account session is invalid, expired, or could not be read."
            ),
            "authenticated": _("Codex reports a valid account session."),
        }.get(status.state, _("Codex account state is unknown."))
        state_label = {
            "not_authenticated": _("Not connected"),
            "login_pending": _("Login pending"),
            "authentication_error": _account_error_state(status.error_code),
            "authenticated": _("Authenticated"),
        }.get(status.state, _("Unknown"))

        if status.connected:
            try:
                usable = asyncio.run(
                    isolated_account_usable(
                        CodexAgentSettings(
                            executable=detected.executable,
                            codex_home=paths.codex_home,
                        )
                    )
                )
            except (CodexAgentError, RuntimeError, OSError, ValueError):
                usable = False
            if usable:
                state_label = _("Authenticated / ready")
                detail = _(
                    "The persistent account is also usable from an isolated product-turn HOME."
                )
            else:
                state_label = _("Authenticated / unusable")
                detail = _(
                    "Codex reports an account, but the isolated product-turn credential copy "
                    "is not usable. Refresh the session or review the installed Codex version."
                )

        values.update(
            codex_account_state=state_label,
            codex_account_identity=status.email or False,
            codex_account_plan=status.plan_type or False,
            codex_account_usage=_format_usage(status.rate_limits) or False,
            codex_account_detail=detail,
        )
        return values

    def _reasoning_setup_message(self, detail):
        if detail == "auth_unavailable":
            return _(
                "Authenticate the installation's primary Codex CLI session and make its "
                "CODEX_HOME available to the Odoo service."
            )
        return super()._reasoning_setup_message(detail)


def _account_error_state(code):
    if code in _INCOMPATIBLE_ERRORS:
        return _("Runtime incompatible")
    if code in _UNUSABLE_ERRORS:
        return _("Runtime unusable")
    return _("Authentication error")


def _account_error_detail(code):
    if code in _INCOMPATIBLE_ERRORS:
        return _("This Codex App Server does not support the required account protocol.")
    if code in _UNUSABLE_ERRORS:
        return _("Codex could not use the private embedded-runtime account storage safely.")
    return _("Codex account state could not be validated safely.")


def _format_usage(rows):
    rendered = []
    for row in rows:
        label = row.get("limit_name") or row.get("limit_id") or _("Codex limit")
        window = row.get("window") or _("window")
        used = row.get("used_percent")
        resets = row.get("resets_at")
        parts = [_("%(used)s%% used") % {"used": used}]
        if type(resets) is int:
            try:
                reset_text = datetime.fromtimestamp(resets, tz=UTC).isoformat(timespec="minutes")
            except (OverflowError, OSError, ValueError):
                reset_text = None
            if reset_text:
                parts.append(reset_text)
        rendered.append(f"{label} / {window}: " + ", ".join(parts))
    return "\n".join(rendered)
