"""Validated Codex model catalog for the Odoo-native chat picker."""

from __future__ import annotations

import re
from typing import Final

from .codex import CodexAgentError, CodexAgentSettings, _CodexClient

MAX_MODEL_OPTIONS: Final = 50
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class CodexModelCatalogError(RuntimeError):
    def __init__(self, code: str = "engine_unavailable") -> None:
        super().__init__(code)
        self.code = code


async def load_codex_model_catalog(settings: CodexAgentSettings) -> dict[str, object]:
    """Query the same local App Server used by turns; no sidecar/network hop is involved."""

    try:
        client = await _CodexClient.start(settings)
        async with client:
            payload = await client.request(
                "model/list",
                {
                    "cursor": None,
                    "limit": MAX_MODEL_OPTIONS,
                    "includeHidden": False,
                },
                timeout=settings.startup_timeout_seconds,
            )
    except (CodexAgentError, OSError, RuntimeError, ValueError):
        raise CodexModelCatalogError() from None

    if not isinstance(payload, dict):
        raise CodexModelCatalogError()
    data = payload.get("data")
    if not isinstance(data, list) or len(data) > MAX_MODEL_OPTIONS:
        raise CodexModelCatalogError()

    models: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            raise CodexModelCatalogError()
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
            raise CodexModelCatalogError()
        seen.add(model)
        models.append(
            {
                "model": model,
                "display_name": display_name,
                "is_default": is_default,
            }
        )

    default_model = (
        settings.model
        if settings.model is not None and _MODEL_PATTERN.fullmatch(settings.model)
        else None
    )
    if default_model is None:
        default_model = next(
            (item["model"] for item in models if item["is_default"]),
            None,
        )
    return {"models": models, "default_model": default_model}
