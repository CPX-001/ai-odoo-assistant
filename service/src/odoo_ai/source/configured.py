"""Effective source-root selection for M7."""

from __future__ import annotations

from collections.abc import Mapping

from odoo_ai.runtime.configuration import load_runtime_admin_overrides
from odoo_ai.source.scanner import source_root_overrides_from_env as deployment_source_roots


def source_root_overrides_from_env(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Use a validated admin selection when present, otherwise deployment roots."""

    deployment_roots = deployment_source_roots(environ)
    overrides = load_runtime_admin_overrides(environ)
    if overrides.source_roots is None:
        return deployment_roots
    return overrides.source_roots
