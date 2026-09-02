"""Provider feature-negotiation metadata independent from one reasoning adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .contracts import CapabilityError, JsonValue

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^[1-9][0-9]*$")


class ProviderFeature(StrEnum):
    STRUCTURED_OUTPUT = "structured_output"
    TOOL_CALLING = "tool_calling"
    ANSWER_STREAMING = "answer_streaming"
    VISION = "vision"
    FILE_INPUT = "file_input"
    WEB = "web"
    LARGE_CONTEXT = "large_context"


class ProviderFeatureState(StrEnum):
    NATIVE = "native"
    EMULATED = "emulated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderFeatureSupport:
    feature: ProviderFeature
    state: ProviderFeatureState
    reason_code: str = ""

    def __post_init__(self) -> None:
        if self.state is ProviderFeatureState.UNAVAILABLE:
            if not self.reason_code or len(self.reason_code) > 128:
                raise CapabilityError("provider_feature_reason_invalid")
        elif self.reason_code:
            raise CapabilityError("provider_feature_reason_invalid")


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Host-known provider capabilities and bounded capacity characteristics."""

    provider_id: str
    features: tuple[ProviderFeatureSupport, ...]
    version: str = "1"
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    max_parallel_requests: int | None = None

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("provider_profile_id_invalid")
        if not _VERSION_RE.fullmatch(self.version):
            raise CapabilityError("provider_profile_version_invalid")
        features = tuple(self.features)
        if any(not isinstance(item, ProviderFeatureSupport) for item in features):
            raise CapabilityError("provider_feature_invalid")
        feature_names = [item.feature for item in features]
        if len(set(feature_names)) != len(feature_names):
            raise CapabilityError("provider_feature_duplicate")
        if set(feature_names) != set(ProviderFeature):
            raise CapabilityError("provider_feature_matrix_incomplete")
        for value in (
            self.context_window_tokens,
            self.max_output_tokens,
            self.max_parallel_requests,
        ):
            if value is not None and (type(value) is not int or value <= 0):
                raise CapabilityError("provider_capacity_invalid")
        object.__setattr__(self, "features", features)

    def support(self, feature: ProviderFeature) -> ProviderFeatureSupport:
        return next(item for item in self.features if item.feature is feature)

    def browser_payload(self) -> dict[str, JsonValue]:
        return {
            "provider_id": self.provider_id,
            "version": self.version,
            "features": [
                {
                    "feature": item.feature.value,
                    "state": item.state.value,
                    "reason_code": item.reason_code or None,
                }
                for item in self.features
            ],
            "capacity": {
                "context_window_tokens": self.context_window_tokens,
                "max_output_tokens": self.max_output_tokens,
                "max_parallel_requests": self.max_parallel_requests,
            },
        }

    def unavailable_features(self) -> tuple[dict[str, JsonValue], ...]:
        return tuple(
            {
                "feature": item.feature.value,
                "reason_code": item.reason_code,
            }
            for item in self.features
            if item.state is ProviderFeatureState.UNAVAILABLE
        )


__all__ = [
    "ProviderFeature",
    "ProviderFeatureState",
    "ProviderFeatureSupport",
    "ProviderProfile",
]
