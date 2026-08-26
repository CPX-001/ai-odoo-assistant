"""Opt-in smoke test for the real Codex App Server selected by deployment."""

import asyncio
import os

import pytest

from odoo_ai.adapters import CodexProbeState, CodexRuntimeSettings, probe_codex_runtime


@pytest.mark.skipif(
    not os.environ.get("ODOO_AI_RUN_CODEX_RUNTIME_SMOKE"),
    reason="real Codex runtime smoke is opt-in",
)
def test_real_codex_app_server_handshake() -> None:
    result = asyncio.run(probe_codex_runtime(CodexRuntimeSettings.from_env()))

    assert result.state is CodexProbeState.COMPATIBLE
    assert result.protocol == "app-server-jsonl-v2"
    assert result.runtime_version
    assert result.auth_state == "unknown"
    assert result.model_state == "unknown"
