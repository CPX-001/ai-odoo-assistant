"""M7 log-provider selection overlays bounded deployment candidates."""

from __future__ import annotations

from collections.abc import Mapping

from odoo_ai.logs.journal import journal_unit_override_from_env as deployment_journal_unit
from odoo_ai.logs.resolution import log_file_override_from_env as deployment_log_file
from odoo_ai.runtime.configuration import load_runtime_admin_overrides


def log_file_override_from_env(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Keep file logs available unless the admin explicitly selected journal."""

    configured = load_runtime_admin_overrides(environ)
    if configured.log_provider == "journal":
        return ()
    return deployment_log_file(environ)


def journal_unit_override_from_env(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Keep journal available unless the admin explicitly selected file."""

    configured = load_runtime_admin_overrides(environment)
    if configured.log_provider == "file":
        return ()
    return deployment_journal_unit(environment)
