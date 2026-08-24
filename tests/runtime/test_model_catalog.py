import asyncio
from pathlib import Path

from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings
from odoo_ai.runtime import model_catalog


def test_model_catalog_uses_model_list_and_cache(monkeypatch) -> None:
    calls = []
    settings = ConfiguredCodexRuntimeSettings(
        executable=Path("/usr/bin/codex"),
        model="gpt-default",
        experimental_api=True,
    )

    class FakeSettings:
        @classmethod
        def from_env(cls):
            return settings

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, params, *, timeout_seconds):
            calls.append((method, params, timeout_seconds))
            return {
                "data": [
                    {
                        "model": "gpt-default",
                        "displayName": "GPT Default",
                        "isDefault": True,
                    },
                    {
                        "model": "gpt-fast",
                        "displayName": "GPT Fast",
                        "isDefault": False,
                    },
                ]
            }

    async def fake_start(settings_value):
        assert settings_value is settings
        return FakeClient()

    monkeypatch.setattr(model_catalog, "ConfiguredCodexRuntimeSettings", FakeSettings)
    monkeypatch.setattr(model_catalog.CodexAppServerClient, "start", fake_start)
    model_catalog._cache = None

    async def run():
        first = await model_catalog.load_codex_model_catalog()
        second = await model_catalog.load_codex_model_catalog()
        return first, second

    first, second = asyncio.run(run())

    assert first is second
    assert first.default_model == "gpt-default"
    assert [item.model for item in first.models] == ["gpt-default", "gpt-fast"]
    assert len(calls) == 1
    assert calls[0][0] == "model/list"
    assert calls[0][1]["includeHidden"] is False
    assert calls[0][1]["limit"] == 50
