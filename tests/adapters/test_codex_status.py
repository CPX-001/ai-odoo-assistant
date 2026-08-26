import asyncio

import pytest

from odoo_ai.adapters import (
    APP_SERVER_PROTOCOL,
    CachedCodexReasoningStatus,
    CodexProbeState,
    CodexRuntimeProbe,
    CodexRuntimeSettings,
)
from odoo_ai.runtime.status import ComponentState


def test_reasoning_probe_is_cached_and_sanitized() -> None:
    calls = 0

    async def probe(settings: CodexRuntimeSettings) -> CodexRuntimeProbe:
        nonlocal calls
        calls += 1
        assert settings.executable is None
        return CodexRuntimeProbe(
            state=CodexProbeState.COMPATIBLE,
            protocol=APP_SERVER_PROTOCOL,
            runtime_version="0.149.0",
            auth_state="available",
            model_state="runtime_default",
        )

    cache = CachedCodexReasoningStatus(
        settings=CodexRuntimeSettings(executable=None),
        ttl_seconds=30,
        probe_loader=probe,
    )

    async def run() -> None:
        first = await cache.inspect()
        second = await cache.inspect()
        assert first == second
        assert first.state is ComponentState.OK
        assert first.detail == "operational"
        assert first.provider == "codex"
        assert first.protocol == APP_SERVER_PROTOCOL
        assert first.runtime_version == "0.149.0"

    asyncio.run(run())
    assert calls == 1


@pytest.mark.parametrize(
    ("probe", "state", "detail"),
    [
        (
            CodexRuntimeProbe(state=CodexProbeState.NOT_CONFIGURED),
            ComponentState.PENDING,
            "not_configured",
        ),
        (
            CodexRuntimeProbe(state=CodexProbeState.NOT_FOUND),
            ComponentState.PENDING,
            "runtime_missing",
        ),
        (
            CodexRuntimeProbe(
                state=CodexProbeState.HANDSHAKE_FAILED,
                error_code="codex_initialize_response_invalid",
            ),
            ComponentState.PENDING,
            "protocol_incompatible",
        ),
        (
            CodexRuntimeProbe(
                state=CodexProbeState.COMPATIBLE,
                auth_state="unavailable",
                error_code="codex_server_error",
            ),
            ComponentState.PENDING,
            "protocol_incompatible",
        ),
        (
            CodexRuntimeProbe(
                state=CodexProbeState.COMPATIBLE,
                auth_state="unavailable",
            ),
            ComponentState.PENDING,
            "auth_unavailable",
        ),
    ],
)
def test_reasoning_probe_maps_degraded_states(
    probe: CodexRuntimeProbe,
    state: ComponentState,
    detail: str,
) -> None:
    async def load(settings: CodexRuntimeSettings) -> CodexRuntimeProbe:
        del settings
        return probe

    cache = CachedCodexReasoningStatus(
        settings=CodexRuntimeSettings(executable=None),
        probe_loader=load,
    )

    result = asyncio.run(cache.inspect())

    assert result.state is state
    assert result.detail == detail
    assert "/" not in result.model_dump_json()
    assert "token" not in result.model_dump_json()
