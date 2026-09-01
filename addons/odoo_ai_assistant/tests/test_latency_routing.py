import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from ..runtime.agent.codex import CodexAgentSettings
from ..runtime.agent.codex_session import ReusableCodexDecisionEngine, _settings_for_decision
from ..runtime.agent.provider_lifecycle import close_reasoning_provider
from ..runtime.agent.reasoning_effort import resolve_auto_reasoning_route


class TestAdaptiveReasoningRouter(TestCase):
    def test_router_starts_light_and_escalates_from_agent_evidence(self):
        light = resolve_auto_reasoning_route(message="Resume este contacto", working_items=())
        self.assertEqual(light.tier, "light")

        balanced = resolve_auto_reasoning_route(
            message="Revisa estos datos",
            working_items=(
                {"kind": "capability_result"},
                {"kind": "capability_result"},
            ),
        )
        self.assertEqual(balanced.tier, "balanced")

        deep = resolve_auto_reasoning_route(
            message="Analiza y ejecuta el plan",
            working_items=(
                {
                    "kind": "host_planning_strategy",
                    "data": {"effective_mode": "deliberate"},
                },
            ),
        )
        self.assertEqual(deep.tier, "deep")

    def test_codex_mapping_is_adapter_specific(self):
        settings = CodexAgentSettings(
            executable=Path("/tmp/codex"),
            codex_home=Path("/tmp/codex-home"),
            reasoning_effort="auto",
        )
        effective, route = _settings_for_decision(
            settings,
            message="Consulta un contacto",
            screen={},
            working_items=(),
        )
        self.assertEqual(route.tier, "light")
        self.assertEqual(effective.reasoning_effort, "low")
        self.assertEqual(settings.reasoning_effort, "auto")


class TestProviderSessionLifecycle(TestCase):
    def test_codex_client_is_started_once_and_closed_once_per_engine(self):
        settings = CodexAgentSettings(
            executable=Path("/tmp/codex"),
            codex_home=Path("/tmp/codex-home"),
        )
        engine = ReusableCodexDecisionEngine(settings)
        fake_client = SimpleNamespace(close=AsyncMock())

        async def exercise():
            with patch(
                "odoo.addons.odoo_ai_assistant.runtime.agent.codex_session._CodexClient.start",
                new=AsyncMock(return_value=fake_client),
            ) as start:
                first, first_reused = await engine._client_for_decision(lambda _point: None)
                second, second_reused = await engine._client_for_decision(lambda _point: None)
                self.assertIs(first, fake_client)
                self.assertIs(second, fake_client)
                self.assertFalse(first_reused)
                self.assertTrue(second_reused)
                self.assertEqual(start.await_count, 1)
                await engine.aclose()
                self.assertEqual(fake_client.close.await_count, 1)

        asyncio.run(exercise())

    def test_generic_lifecycle_reaches_inner_provider(self):
        inner = SimpleNamespace(aclose=AsyncMock())
        wrapped = SimpleNamespace(_provider=SimpleNamespace(_provider=inner))
        asyncio.run(close_reasoning_provider(wrapped))
        self.assertEqual(inner.aclose.await_count, 1)
