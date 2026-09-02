"""Provider-neutral projection of active Skills, JIT context and Evidence into one model decision.

This wrapper is deliberately non-authoritative. Skills are trusted behavior guidance from
installed code, JIT context/current-screen semantics and retrieved Evidence are data, and the
EffectiveAssistantManifest is a derived host projection. Executable authority remains the
CapabilityRegistry/Executor/Policy path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace

from ...services.screen_context import enrich_runtime_screen
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
from ..capabilities.evidence import (
    EvidenceLedger,
    EvidenceSearchRequest,
    thaw_json,
)
from ..capabilities.evidence_runtime import AssistantEvidenceDecisionEngine
from ..capabilities.knowledge_routing import CompanyKnowledgeEvidenceRoutingPolicy
from .contracts import NextDecision

_CACHE_METADATA_KEYS = (
    "capability_enabled",
    "context_provider_enabled",
    "skill_enabled",
)


class AssistantExtensionDecisionEngine:
    """Inject active extension guidance/context without granting execution authority.

    The wrapper is created for one host decision loop. Expensive host projections that are stable
    for that turn (resolved screen semantics, configuration health and the manifest projection) are
    memoized locally. JIT ContextProvider contributions remain fresh on every model decision.
    Evidence retrieval is question-sensitive, bounded and provider-neutral; generic turns do not
    pre-retrieve it, and retrieved content is always projected through the untrusted-data partition.
    """

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
        self._screen_cache_key = None
        self._screen_cache_value = None
        self._manifest_cache_key = None
        self._manifest_cache_value = None
        self._configuration_health_cache = None
        self._evidence_routing = CompanyKnowledgeEvidenceRoutingPolicy()
        self._evidence_engine = AssistantEvidenceDecisionEngine(
            extensions.evidence_providers,
            routing_policy=self._evidence_routing,
        )
        self._evidence_ledger = EvidenceLedger()

    def browser_citations(self) -> list[dict[str, object]]:
        """Return bounded public provenance metadata without retrieved content."""

        return [
            {
                "evidence_id": ref.evidence_id,
                "kind": ref.kind.value,
                "title": ref.title,
                "provenance": ref.provenance,
                "freshness": ref.freshness.value,
                "citation": thaw_json(ref.citation),
            }
            for ref in self._evidence_ledger.snapshot().refs[-24:]
        ]

    async def next_decision(self, **kwargs) -> NextDecision:
        context = kwargs.get("context")
        working_items = kwargs.get("working_items", ())
        reasoning = kwargs.get("reasoning_capabilities", ())
        planning = kwargs.get("planning_capabilities", ())
        message = kwargs.get("message")
        if not isinstance(context, CapabilityContext):
            raise CapabilityError("assistant_extension_context_invalid")
        if not isinstance(working_items, tuple):
            working_items = tuple(working_items)

        context, screen_key = self._context_with_enriched_screen(context)
        model_visible_names = tuple(
            sorted(
                {
                    item.name
                    for item in (*tuple(reasoning), *tuple(planning))
                    if hasattr(item, "name")
                }
            )
        )

        # Context providers are intentionally JIT. Even though Skills/availability are usually
        # stable for the turn, collection may expose changing installation/runtime context.
        active = self._extensions.activate(
            context,
            capability_names=model_visible_names,
        )
        manifest_payload = self._manifest_payload(
            context,
            screen_key=screen_key,
            model_visible_names=model_visible_names,
            evidence_provider_ids=active.evidence_provider_ids,
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

        evidence_host_item = None
        evidence_working_items: tuple[dict[str, object], ...] = ()
        if (
            isinstance(message, str)
            and message.strip()
            and active.evidence_provider_ids
        ):
            probe = EvidenceSearchRequest(query=message)
            if self._evidence_routing.should_retrieve(probe):
                request = EvidenceSearchRequest(
                    query=message,
                    provider_ids=active.evidence_provider_ids,
                    max_results=16,
                    max_excerpt_bytes=8 * 1024,
                    max_total_bytes=64 * 1024,
                )
                evidence = self._evidence_engine.collect(
                    context,
                    request,
                    ledger=self._evidence_ledger,
                )
                evidence_host_item = {
                    "kind": "host_assistant_evidence",
                    "source": "host",
                    "data": evidence.host_contract(),
                }
                evidence_working_items = tuple(
                    {
                        "kind": "assistant_evidence",
                        "source": "evidence",
                        "data": item,
                    }
                    for item in evidence.untrusted_data()
                )

        provider_kwargs = dict(kwargs)
        provider_kwargs["context"] = context
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
                "data": manifest_payload,
            },
            *((evidence_host_item,) if evidence_host_item is not None else ()),
            *(
                {
                    "kind": "assistant_context",
                    "source": "context",
                    "provider_id": item["provider_id"],
                    "data": item["data"],
                }
                for item in active.untrusted_context_data()
            ),
            *evidence_working_items,
        )
        return await self._provider.next_decision(**provider_kwargs)

    def _context_with_enriched_screen(self, context: CapabilityContext):
        key = _screen_projection_key(context)
        if key is not None and key == self._screen_cache_key and self._screen_cache_value is not None:
            enriched = deepcopy(self._screen_cache_value)
        else:
            enriched = enrich_runtime_screen(context.env, context.screen)
            if key is not None:
                self._screen_cache_key = key
                self._screen_cache_value = deepcopy(enriched)
        return replace(context, screen=enriched), key

    def _configuration_health(self):
        if self._configuration_health_cache is None:
            rows = list(_configuration_health(self._registry, self._config))
            rows.extend(
                {
                    "provider_id": item.provider_id,
                    "state": f"extension_{item.state}",
                    "error_code": item.error_code or None,
                }
                for item in self._extensions.statuses
                if item.state != "loaded"
            )
            self._configuration_health_cache = tuple(rows)
        return deepcopy(self._configuration_health_cache)

    def _manifest_payload(
        self,
        context: CapabilityContext,
        *,
        screen_key,
        model_visible_names: tuple[str, ...],
        evidence_provider_ids: tuple[str, ...],
    ) -> dict[str, object]:
        key = _manifest_projection_key(
            context,
            screen_key=screen_key,
            model_visible_names=model_visible_names,
            evidence_provider_ids=evidence_provider_ids,
        )
        if key is not None and key == self._manifest_cache_key and self._manifest_cache_value is not None:
            return deepcopy(self._manifest_cache_value)

        manifest = build_effective_assistant_manifest(
            registry=self._registry,
            context=context,
            provider_profile=self._provider_profile,
            skills=self._extensions.skills,
            context_providers=self._extensions.context_providers,
            evidence_provider_ids=evidence_provider_ids,
            technical_profile=self._technical_profile,
            configuration_health=self._configuration_health(),
        )
        payload = _provider_manifest(manifest.browser_payload())
        if key is not None:
            self._manifest_cache_key = key
            self._manifest_cache_value = deepcopy(payload)
        return payload


def _screen_projection_key(context: CapabilityContext):
    encoded = _canonical_json(context.screen)
    if encoded is None:
        return None
    return (id(context.env), context.turn_id, encoded)


def _manifest_projection_key(
    context: CapabilityContext,
    *,
    screen_key,
    model_visible_names: tuple[str, ...],
    evidence_provider_ids: tuple[str, ...],
):
    if screen_key is None:
        return None
    metadata = {
        key: context.metadata.get(key)
        for key in _CACHE_METADATA_KEYS
        if key in context.metadata
    }
    encoded_metadata = _canonical_json(metadata)
    if encoded_metadata is None:
        return None
    return (
        screen_key,
        model_visible_names,
        tuple(evidence_provider_ids),
        encoded_metadata,
    )


def _canonical_json(value: object) -> str | None:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return None


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
    evidence_provider_ids = payload.get("evidence_provider_ids")
    health = payload.get("configuration_health")
    return {
        "provider": payload.get("provider"),
        "technical_profile": payload.get("technical_profile"),
        "skills": list(skills) if isinstance(skills, list) else [],
        "context_providers": list(contexts) if isinstance(contexts, list) else [],
        "evidence_provider_ids": (
            list(evidence_provider_ids)
            if isinstance(evidence_provider_ids, list)
            else []
        ),
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
