"""Validated Codex model catalog for the Odoo-native chat picker."""

from __future__ import annotations

import re
from typing import Final

from .codex import CodexAgentError, CodexAgentSettings, _CodexClient

MAX_MODEL_OPTIONS: Final = 50
MAX_REASONING_EFFORTS: Final = 12
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_EFFORT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_NAMED_VARIANT_PATTERN = re.compile(
    r"^(?P<family>gpt-\d+(?:\.\d+)+)-(?P<variant>sol|terra|luna)$",
    re.IGNORECASE,
)
_BARE_GPT_FAMILY_PATTERN = re.compile(r"^gpt-\d+(?:\.\d+)+$", re.IGNORECASE)


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

    return parse_codex_model_catalog(payload, configured_model=settings.model)


def parse_codex_model_catalog(payload, *, configured_model=None) -> dict[str, object]:
    """Validate provider metadata and add UI-only family/variant grouping hints.

    ``model/list`` remains provider authority for the exact selectable model ids and
    supported reasoning efforts. Family/variant fields are presentation metadata only;
    they never authorize a model that the provider did not return.
    """

    if not isinstance(payload, dict):
        raise CodexModelCatalogError()
    data = payload.get("data")
    if not isinstance(data, list) or len(data) > MAX_MODEL_OPTIONS:
        raise CodexModelCatalogError()

    raw_models: list[dict[str, object]] = []
    seen: set[str] = set()
    named_families: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            raise CodexModelCatalogError()
        model = item.get("model")
        display_name = item.get("displayName")
        description = item.get("description", "")
        is_default = item.get("isDefault", False)
        if (
            not isinstance(model, str)
            or not _MODEL_PATTERN.fullmatch(model)
            or model in seen
            or not isinstance(display_name, str)
            or not 1 <= len(display_name) <= 160
            or not isinstance(description, str)
            or len(description) > 512
            or not isinstance(is_default, bool)
        ):
            raise CodexModelCatalogError()
        efforts, default_effort = _reasoning_metadata(item)
        match = _NAMED_VARIANT_PATTERN.fullmatch(model)
        if match:
            named_families.add(match.group("family").lower())
        seen.add(model)
        raw_models.append(
            {
                "model": model,
                "display_name": display_name,
                "description": description,
                "supported_reasoning_efforts": efforts,
                "default_reasoning_effort": default_effort,
                "is_default": is_default,
            }
        )

    models = []
    for item in raw_models:
        family, variant, family_alias = _family_metadata(
            item["model"],
            named_families=named_families,
        )
        models.append(
            {
                **item,
                "family": family,
                "variant": variant,
                "family_alias": family_alias,
            }
        )

    default_model = (
        configured_model
        if isinstance(configured_model, str)
        and _MODEL_PATTERN.fullmatch(configured_model)
        else None
    )
    if default_model is None:
        default_model = next(
            (item["model"] for item in models if item["is_default"]),
            None,
        )
    return {"models": models, "default_model": default_model}


def _reasoning_metadata(item):
    raw = item.get("supportedReasoningEfforts", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list) or len(raw) > MAX_REASONING_EFFORTS:
        raise CodexModelCatalogError()
    efforts: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise CodexModelCatalogError()
        effort = entry.get("reasoningEffort")
        description = entry.get("description", "")
        if (
            not isinstance(effort, str)
            or not _EFFORT_PATTERN.fullmatch(effort)
            or effort in seen
            or not isinstance(description, str)
            or len(description) > 512
        ):
            raise CodexModelCatalogError()
        seen.add(effort)
        efforts.append({"effort": effort, "description": description})

    default = item.get("defaultReasoningEffort")
    if default is not None and (
        not isinstance(default, str)
        or not _EFFORT_PATTERN.fullmatch(default)
        or default not in seen
    ):
        raise CodexModelCatalogError()
    return efforts, default


def _family_metadata(model, *, named_families):
    match = _NAMED_VARIANT_PATTERN.fullmatch(model)
    if match:
        return match.group("family"), match.group("variant").lower(), False
    lowered = model.lower()
    if _BARE_GPT_FAMILY_PATTERN.fullmatch(model) and lowered in named_families:
        # The bare family alias is the flagship/Sol route for the currently exposed
        # named-variant families. Keep the exact provider id but avoid a duplicate top-level row.
        return model, "sol", True
    return model, None, False
