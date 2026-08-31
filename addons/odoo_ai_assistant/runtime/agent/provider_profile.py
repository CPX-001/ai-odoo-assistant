"""Current effective provider-feature profile for the embedded Codex adapter.

The profile describes features the Odoo Assistant can actually use through the current
adapter, not every feature the upstream Codex product may expose elsewhere.  It is
metadata only: it never grants capability or execution authority.
"""

from __future__ import annotations

from ..capabilities import (
    ProviderFeature,
    ProviderFeatureState,
    ProviderFeatureSupport,
    ProviderProfile,
)


def current_codex_provider_profile() -> ProviderProfile:
    """Return conservative host-known feature support for the current App Server seam."""

    states = {
        ProviderFeature.STRUCTURED_OUTPUT: (
            ProviderFeatureState.NATIVE,
            "",
        ),
        ProviderFeature.TOOL_CALLING: (
            ProviderFeatureState.EMULATED,
            "",
        ),
        ProviderFeature.ANSWER_STREAMING: (
            ProviderFeatureState.NATIVE,
            "",
        ),
        ProviderFeature.VISION: (
            ProviderFeatureState.UNAVAILABLE,
            "assistant_vision_not_exposed",
        ),
        ProviderFeature.FILE_INPUT: (
            ProviderFeatureState.UNAVAILABLE,
            "assistant_file_input_not_exposed",
        ),
        ProviderFeature.WEB: (
            ProviderFeatureState.UNAVAILABLE,
            "provider_native_web_not_exposed",
        ),
        ProviderFeature.LARGE_CONTEXT: (
            ProviderFeatureState.UNAVAILABLE,
            "provider_context_capacity_unverified",
        ),
    }
    return ProviderProfile(
        provider_id="openai.codex_app_server",
        version="1",
        features=tuple(
            ProviderFeatureSupport(
                feature=feature,
                state=states[feature][0],
                reason_code=states[feature][1],
            )
            for feature in ProviderFeature
        ),
    )


__all__ = ["current_codex_provider_profile"]
