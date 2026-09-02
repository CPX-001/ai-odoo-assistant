"""Bounded just-in-time context provider contracts for the Assistant runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .contracts import (
    CapabilityContext,
    CapabilityError,
    JsonValue,
    freeze_contract_mapping,
    thaw_contract_json,
)

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^[1-9][0-9]*$")

type ContextCollector = Callable[[CapabilityContext], Mapping[str, JsonValue]]


@dataclass(frozen=True, slots=True)
class ContextProvider:
    """Trusted provider of bounded JIT context.

    Returned context remains data. It cannot grant capability availability, approval or
    execution authority and is re-evaluated against the current effective Environment.
    """

    provider_id: str
    description: str
    collect: ContextCollector = field(repr=False, compare=False)
    title: str = ""
    version: str = "1"
    optional: bool = True
    default_enabled: bool = True
    max_output_bytes: int = 24 * 1024
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("context_provider_id_invalid")
        if not _VERSION_RE.fullmatch(self.version):
            raise CapabilityError("context_provider_version_invalid")
        if not self.description.strip() or len(self.description) > 4_000:
            raise CapabilityError("context_provider_description_invalid")
        if self.title and len(self.title) > 160:
            raise CapabilityError("context_provider_title_invalid")
        if not 512 <= self.max_output_bytes <= 256 * 1024:
            raise CapabilityError("context_provider_output_limit_invalid")
        if not callable(self.collect):
            raise CapabilityError("context_provider_collector_invalid")
        object.__setattr__(self, "metadata", freeze_contract_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ContextContribution:
    provider_id: str
    data: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("context_provider_id_invalid")
        object.__setattr__(self, "data", freeze_contract_mapping(self.data))


@dataclass(frozen=True, slots=True)
class ContextProviderStatus:
    provider_id: str
    state: str
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.state not in {"loaded", "failed"}:
            raise CapabilityError("context_provider_state_invalid")
        if self.state == "loaded" and self.error_code:
            raise CapabilityError("context_provider_state_invalid")
        if self.state == "failed" and not self.error_code:
            raise CapabilityError("context_provider_state_invalid")


class ContextProviderCatalog:
    """Immutable context-provider catalog with bounded fail-isolated collection."""

    def __init__(self, providers: Iterable[ContextProvider] = ()) -> None:
        by_id: dict[str, ContextProvider] = {}
        for provider in sorted(providers, key=lambda item: item.provider_id):
            if provider.provider_id in by_id:
                raise CapabilityError("context_provider_id_duplicate")
            by_id[provider.provider_id] = provider
        self._by_id = by_id

    @property
    def providers(self) -> tuple[ContextProvider, ...]:
        return tuple(self._by_id.values())

    def resolve(self, provider_id: str) -> ContextProvider:
        try:
            return self._by_id[provider_id]
        except KeyError:
            raise CapabilityError("context_provider_not_registered") from None

    def available(self, context: CapabilityContext) -> tuple[ContextProvider, ...]:
        return tuple(item for item in self.providers if _provider_enabled(item, context))

    def catalog(self, context: CapabilityContext) -> tuple[dict[str, JsonValue], ...]:
        available_ids = {item.provider_id for item in self.available(context)}
        return tuple(
            {
                "provider_id": item.provider_id,
                "title": item.title or item.provider_id,
                "description": item.description,
                "version": item.version,
                "optional": item.optional,
                "available": item.provider_id in available_ids,
            }
            for item in self.providers
        )

    def collect(
        self,
        context: CapabilityContext,
        *,
        provider_ids: Iterable[str] | None = None,
    ) -> tuple[tuple[ContextContribution, ...], tuple[ContextProviderStatus, ...]]:
        if provider_ids is None:
            selected = self.available(context)
        else:
            selected = tuple(self.resolve(provider_id) for provider_id in provider_ids)
            selected = tuple(item for item in selected if _provider_enabled(item, context))

        contributions: list[ContextContribution] = []
        statuses: list[ContextProviderStatus] = []
        for provider in selected:
            try:
                raw = provider.collect(context)
                data = _validated_payload(raw, provider.max_output_bytes)
            except Exception as error:  # trusted boundary; never expose raw provider failures
                code = error.code if isinstance(error, CapabilityError) else "context_provider_load_failed"
                if not provider.optional:
                    raise CapabilityError(code) from error
                statuses.append(
                    ContextProviderStatus(
                        provider_id=provider.provider_id,
                        state="failed",
                        error_code=code,
                    )
                )
                continue
            contributions.append(ContextContribution(provider_id=provider.provider_id, data=data))
            statuses.append(ContextProviderStatus(provider_id=provider.provider_id, state="loaded"))
        return tuple(contributions), tuple(statuses)


def _validated_payload(
    value: Mapping[str, JsonValue],
    max_output_bytes: int,
) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise CapabilityError("context_provider_payload_invalid")
    data = freeze_contract_mapping(value)
    try:
        encoded = json.dumps(
            thaw_contract_json(data),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CapabilityError("context_provider_payload_invalid") from error
    if len(encoded) > max_output_bytes:
        raise CapabilityError("context_provider_payload_too_large")
    return data


def _provider_enabled(provider: ContextProvider, context: CapabilityContext) -> bool:
    overrides = context.metadata.get("context_provider_enabled", {})
    if not isinstance(overrides, dict):
        overrides = {}
    exact = overrides.get(provider.provider_id)
    if isinstance(exact, bool):
        return exact
    namespace = provider.provider_id.rpartition(".")[0]
    while namespace:
        value = overrides.get(namespace + ".*")
        if isinstance(value, bool):
            return value
        namespace = namespace.rpartition(".")[0]
    return provider.default_enabled


__all__ = [
    "ContextCollector",
    "ContextContribution",
    "ContextProvider",
    "ContextProviderCatalog",
    "ContextProviderStatus",
]
