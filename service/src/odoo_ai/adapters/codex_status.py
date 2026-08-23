"""Cached, sanitized Codex readiness adapter for admin status."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from odoo_ai.adapters.codex_runtime import (
    CodexProbeState,
    CodexRuntimeProbe,
    CodexRuntimeSettings,
    probe_codex_readiness,
)
from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings
from odoo_ai.runtime.configuration import current_runtime_config_revision
from odoo_ai.runtime.status import ComponentState, ReasoningComponentStatus

DEFAULT_REASONING_PROBE_TTL_SECONDS = 30.0
CODEX_READINESS_TTL_ENV = "ODOO_AI_CODEX_READINESS_TTL_SECONDS"

type ProbeLoader = Callable[[CodexRuntimeSettings], Awaitable[CodexRuntimeProbe]]


@dataclass(slots=True)
class CachedCodexReasoningStatus:
    """Run a cheap account/handshake probe at most once per short TTL/config revision."""

    settings: ConfiguredCodexRuntimeSettings
    ttl_seconds: float = DEFAULT_REASONING_PROBE_TTL_SECONDS
    probe_loader: ProbeLoader = probe_codex_readiness
    _cached: ReasoningComponentStatus | None = field(default=None, init=False)
    _expires_at: float = field(default=0.0, init=False)
    _config_revision: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        if not 0.1 <= self.ttl_seconds <= 300:
            raise ValueError("codex_readiness_ttl_invalid")

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> CachedCodexReasoningStatus:
        source = os.environ if environ is None else environ
        raw_ttl = source.get(CODEX_READINESS_TTL_ENV)
        try:
            ttl = DEFAULT_REASONING_PROBE_TTL_SECONDS if raw_ttl is None else float(raw_ttl)
        except ValueError:
            raise ValueError("codex_readiness_ttl_invalid") from None
        result = cls(
            settings=ConfiguredCodexRuntimeSettings.from_env(environ),
            ttl_seconds=ttl,
        )
        result._config_revision = current_runtime_config_revision(environ)
        return result

    async def inspect(self) -> ReasoningComponentStatus:
        now = time.monotonic()
        revision = current_runtime_config_revision()
        if (
            self._cached is not None
            and now < self._expires_at
            and revision == self._config_revision
        ):
            return self._cached
        async with self._lock:
            revision = current_runtime_config_revision()
            if revision != self._config_revision:
                self.settings = ConfiguredCodexRuntimeSettings.from_env()
                self._cached = None
                self._expires_at = 0.0
                self._config_revision = revision
            now = time.monotonic()
            if self._cached is not None and now < self._expires_at:
                return self._cached
            probe = await self.probe_loader(self.settings)
            status = _component_from_probe(probe)
            self._cached = status
            self._expires_at = time.monotonic() + self.ttl_seconds
            return status


def _component_from_probe(probe: CodexRuntimeProbe) -> ReasoningComponentStatus:
    if probe.state is CodexProbeState.NOT_CONFIGURED:
        return _status(probe, ComponentState.PENDING, "not_configured")
    if probe.state is CodexProbeState.NOT_FOUND:
        return _status(probe, ComponentState.PENDING, "runtime_missing")
    if probe.state is CodexProbeState.HANDSHAKE_FAILED:
        detail = (
            "protocol_incompatible"
            if probe.error_code is not None
            and (
                "protocol" in probe.error_code
                or "response" in probe.error_code
                or "initialize" in probe.error_code
            )
            else "error"
        )
        return _status(probe, ComponentState.PENDING, detail)
    if probe.auth_state == "unavailable" and probe.error_code is not None:
        return _status(probe, ComponentState.PENDING, "protocol_incompatible")
    if probe.auth_state in {"available", "not_required"}:
        return _status(probe, ComponentState.OK, "operational")
    if probe.auth_state == "unknown" and probe.error_code is not None:
        return _status(probe, ComponentState.PENDING, "error")
    return _status(probe, ComponentState.PENDING, "auth_unavailable")


def _status(
    probe: CodexRuntimeProbe, state: ComponentState, detail: str
) -> ReasoningComponentStatus:
    return ReasoningComponentStatus(
        state=state,
        detail=detail,
        provider="codex",
        protocol=probe.protocol,
        runtime_version=probe.runtime_version,
        model=probe.model,
    )
