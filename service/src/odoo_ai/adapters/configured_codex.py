"""Effective Codex runtime settings with bounded M7 administrative overlays."""

from __future__ import annotations

import re
from collections.abc import Mapping

from odoo_ai.adapters.codex_runtime import CodexRuntimeSettings as HostCodexRuntimeSettings
from odoo_ai.adapters.codex_runtime import CodexRuntimeConfigurationError
from odoo_ai.runtime.configuration import load_runtime_admin_overrides

_MODEL = re.compile(r"^[A-Za-z0-9_.:/-]+$")


class ConfiguredCodexRuntimeSettings(HostCodexRuntimeSettings):
    """Preserve host-owned runtime authority and overlay only registered M7 keys."""

    def __post_init__(self) -> None:
        for path in (self.executable, self.codex_home, self.isolated_cwd):
            if path is not None and not path.is_absolute():
                raise CodexRuntimeConfigurationError("codex_path_must_be_absolute")
        if self.model is not None and (
            not self.model.strip()
            or self.model != self.model.strip()
            or len(self.model) > 128
            or any(character in self.model for character in "\r\n\0")
            or _MODEL.fullmatch(self.model) is None
        ):
            raise CodexRuntimeConfigurationError("codex_model_invalid")
        if not 0 < self.startup_timeout_seconds <= 120:
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
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> ConfiguredCodexRuntimeSettings:
        host = HostCodexRuntimeSettings.from_env(environ)
        overrides = load_runtime_admin_overrides(environ)
        return cls(
            executable=host.executable,
            codex_home=host.codex_home,
            model=(
                overrides.reasoning_model
                if overrides.reasoning_model is not None
                else host.model
            ),
            isolated_cwd=host.isolated_cwd,
            startup_timeout_seconds=(
                overrides.reasoning_startup_timeout_seconds
                if overrides.reasoning_startup_timeout_seconds is not None
                else host.startup_timeout_seconds
            ),
            turn_timeout_seconds=(
                overrides.reasoning_turn_timeout_seconds
                if overrides.reasoning_turn_timeout_seconds is not None
                else host.turn_timeout_seconds
            ),
            shutdown_timeout_seconds=host.shutdown_timeout_seconds,
            max_frame_bytes=host.max_frame_bytes,
            max_stdout_bytes=host.max_stdout_bytes,
            max_stderr_bytes=host.max_stderr_bytes,
            experimental_api=host.experimental_api,
        )
