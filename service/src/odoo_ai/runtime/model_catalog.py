"""Small cached Codex model catalog for the Odoo chat picker."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Final

from odoo_ai.adapters.codex_runtime import (
    CodexAppServerClient,
    CodexRuntimeError,
)
from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings

MODEL_CATALOG_TTL_SECONDS: Final = 300.0
MAX_MODEL_OPTIONS: Final = 50
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class RuntimeModelCatalogError(RuntimeError):
    def __init__(self, code: str = "engine_unavailable") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ModelOption:
    model: str
    display_name: str
    is_default: bool

    def to_mapping(self) -> dict[str, object]:
        return {
            "model": self.model,
            "display_name": self.display_name,
            "is_default": self.is_default,
        }


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    models: tuple[ModelOption, ...]
    default_model: str | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "models": [item.to_mapping() for item in self.models],
            "default_model": self.default_model,
        }


_cache: tuple[float, ModelCatalog] | None = None
_cache_lock = asyncio.Lock()


async def load_codex_model_catalog() -> ModelCatalog:
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < MODEL_CATALOG_TTL_SECONDS:
        return _cache[1]

    async with _cache_lock:
        now = time.monotonic()
        if _cache is not None and now - _cache[0] < MODEL_CATALOG_TTL_SECONDS:
            return _cache[1]
        catalog = await _fetch_catalog()
        _cache = (now, catalog)
        return catalog


async def _fetch_catalog() -> ModelCatalog:
    try:
        settings = ConfiguredCodexRuntimeSettings.from_env()
        client = await CodexAppServerClient.start(settings)
        async with client:
            payload = await client.request(
                "model/list",
                {
                    "cursor": None,
                    "limit": MAX_MODEL_OPTIONS,
                    "includeHidden": False,
                },
                timeout_seconds=settings.startup_timeout_seconds,
            )
    except (CodexRuntimeError, OSError, RuntimeError, ValueError):
        raise RuntimeModelCatalogError() from None

    if not isinstance(payload, dict):
        raise RuntimeModelCatalogError()
    data = payload.get("data")
    if not isinstance(data, list) or len(data) > MAX_MODEL_OPTIONS:
        raise RuntimeModelCatalogError()

    options: list[ModelOption] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            raise RuntimeModelCatalogError()
        model = item.get("model")
        display_name = item.get("displayName")
        is_default = item.get("isDefault", False)
        if (
            not isinstance(model, str)
            or not _MODEL_PATTERN.fullmatch(model)
            or model in seen
            or not isinstance(display_name, str)
            or not 1 <= len(display_name) <= 160
            or not isinstance(is_default, bool)
        ):
            raise RuntimeModelCatalogError()
        seen.add(model)
        options.append(
            ModelOption(
                model=model,
                display_name=display_name,
                is_default=is_default,
            )
        )

    default_model = settings.model if settings.model and _MODEL_PATTERN.fullmatch(settings.model) else None
    if default_model is None:
        default_model = next((item.model for item in options if item.is_default), None)
    return ModelCatalog(models=tuple(options), default_model=default_model)
