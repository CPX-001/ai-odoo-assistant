"""Provider-neutral projection of active Skills and JIT context into one model decision.

This wrapper is deliberately non-authoritative.  Skills are trusted behavior guidance from
installed code, JIT context is untrusted data, and the EffectiveAssistantManifest is a derived
host projection.  Executable authority remains the CapabilityRegistry/Executor/Policy path.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..capabilities import (
    AssistantExtensionCatalog,
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityError,
    CapabilityRegistry,
    ProviderProfile,
    TechnicalAccessProfile,
    build_effective_assistant_manifest,
)
from .contracts import NextDecision


class AssistantExtensionDecisionEngine:
    """Inject active extension guidance/context without persisting it as transcript state."""

    def __init__(
        self,
        provider,
        *,
        registry: CapabilityRegistry,
        extensions: AssistantExtensionCatalog,
        provider_profile: ProviderProfile,
        config: CapabilityConfigResolver,
        technical_profile: TechnicalAccessProfile,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._extensions = extensions
        self._provider_profile = provider_profile
        self._config = config
        self._technical_profile = technical_profile

    async def next_decision(self, **kwargs) -> NextDecision:
        context = kwargs.get("context")
        working_items = kwargs.get("working_items", ())
        reasoning = kwargs.get("reasoning_capabilities", ())
        planning = kwargs.get("planning_capabilities", ())
        if not isinstance(context, CapabilityContext):
            raise CapabilityError("assistant_extension_context_invalid")
        if not isinstance(working_items, tuple):
            working_items = tuple(working_items)

        model_visible_names = tuple(
            sorted(
                {
                    item.name
                    for item in (*tuple(reasoning), *tuple(planning))
                    if hasattr(item, "name")
                }
            )
        )
        active = self._extensions.activate(
            context,
            capability_names=model_visible_names,
        )
        configuration_health = list(_configuration_health(self._registry, self._config))
        configuration_health.extend(
            {
                "provider_id": item.provider_id,
                "state": f"extension_{item.state}",
                "error_code": item.error_code or None,
            }
            for item in self._extensions.statuses
            if item.state != "loaded"
        )
        manifest = build_effective_assistant_manifest(
            registry=self._registry,
            context=context,
            provider_profile=self._provider_profile,
            skills=self._extensions.skills,
            context_providers=self._extensions.context_providers,
            technical_profile=self._technical_profile,
            configuration_health=configuration_health,
        )

        extension_contract = {
            "skills": list(active.host_skill_contract()),
            "context_statuses": [
                {
                    "provider_id": item.provider_id,
                    "state": item.state,
                    "error_code": item.error_code or None,
                }
                for item in active.context_statuses
            ],
        }
        provider_kwargs = dict(kwargs)
        provider_kwargs["working_items"] = (
            *working_items,
            {
                "kind": "host_assistant_extensions",
                "source": "host",
                "data": extension_contract,
            },
            {
                "kind": "host_assistant_manifest",
                "source": "host",
                "data": _provider_manifest(manifest.browser_payload()),
            },
            *(
                {
                    "kind": "assistant_context",
                    "source": "context",
                    "provider_id": item["provider_id"],
                    "data": item["data"],
                }
                for item in active.untrusted_context_data()
            ),
        )
        return await self._provider.next_decision(**provider_kwargs)


def _configuration_health(
    registry: CapabilityRegistry,
    config: CapabilityConfigResolver,
) -> tuple[dict[str, object], ...]:
    """Expose only sanitized configuration state, never configured/secret values."""

    rows = []
    for definition in registry.definitions:
        try:
            config.resolve(definition)
        except CapabilityError as error:
            state = (
                "missing_configuration"
                if error.code == "capability_configuration_missing"
                else "invalid_configuration"
            )
            rows.append(
                {
                    "capability": definition.name,
                    "state": state,
                    "error_code": error.code,
                }
            )
    return tuple(rows)


def _provider_manifest(payload: Mapping[str, object]) -> dict[str, object]:
    """Keep the self-description useful without duplicating full capability schemas."""

    skills = payload.get("skills")
    contexts = payload.get("context_providers")
    health = payload.get("configuration_health")
    return {
        "provider": payload.get("provider"),
        "technical_profile": payload.get("technical_profile"),
        "skills": list(skills) if isinstance(skills, list) else [],
        "context_providers": list(contexts) if isinstance(contexts, list) else [],
        "configuration_health": [
            item
            for item in (health if isinstance(health, list) else [])
            if isinstance(item, dict)
            and item.get("state") not in {"loaded", "ready"}
        ],
        "unavailable_features": payload.get("unavailable_features") or [],
        "disclosure": payload.get("disclosure") or {},
    }


__all__ = ["AssistantExtensionDecisionEngine"]
