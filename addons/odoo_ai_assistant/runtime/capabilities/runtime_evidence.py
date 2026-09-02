"""Bounded runtime/installation Evidence from the effective Odoo Environment."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from .contracts import CapabilityContext, CapabilityError, JsonValue
from .evidence import (
    EvidenceAccessScope,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidenceProvider,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    EvidenceTrust,
    canonical_fingerprint,
)

PROVIDER_ID = "assistant.runtime_inventory"
SOURCE_ID = "odoo.installation"
MAX_MODULES = 96


def _env(context: CapabilityContext):
    env = getattr(context, "env", None)
    if env is None:
        raise CapabilityError("runtime_inventory_env_unavailable")
    return env


def _is_technical(context: CapabilityContext) -> bool:
    profile = getattr(context, "technical_profile", None)
    value = getattr(profile, "value", profile)
    if isinstance(value, str) and value.casefold() in {
        "technical",
        "developer",
        "operator",
    }:
        return True
    user = getattr(getattr(context, "env", None), "user", None)
    try:
        return bool(user and user.has_group("base.group_system"))
    except Exception:
        return False


def _database_identity(env) -> str:
    dbname = str(getattr(getattr(env, "cr", None), "dbname", "unknown"))
    return hashlib.sha256(dbname.encode("utf-8")).hexdigest()[:16]


def _release_payload() -> dict[str, JsonValue]:
    try:
        from odoo import release

        return {
            "version": str(getattr(release, "version", "unknown")),
            "version_info": [
                str(item) for item in getattr(release, "version_info", ())
            ],
            "series": str(getattr(release, "series", "")),
            "edition": "community",
        }
    except Exception:
        return {
            "version": "unknown",
            "version_info": [],
            "series": "",
            "edition": "community",
        }


def _module_payload(env, *, technical: bool) -> tuple[list[dict[str, JsonValue]], bool]:
    """Read only installed-module metadata through the effective user Environment."""

    module_model = env["ir.module.module"]
    available_fields = set(getattr(module_model, "_fields", {}))
    field_names = ["name", "state"]
    for field_name in (
        "shortdesc",
        "installed_version",
        "latest_version",
        "author",
        "license",
    ):
        if field_name in available_fields:
            field_names.append(field_name)
    records = module_model.search_read(
        [("state", "=", "installed")],
        fields=field_names,
        order="name asc",
        limit=MAX_MODULES + 1,
    )
    result: list[dict[str, JsonValue]] = []
    for record in records[:MAX_MODULES]:
        item: dict[str, JsonValue] = {
            "name": str(record.get("name") or ""),
            "state": str(record.get("state") or ""),
            "title": str(record.get("shortdesc") or ""),
            "installed_version": str(record.get("installed_version") or ""),
        }
        if technical:
            item.update(
                {
                    "latest_version": str(record.get("latest_version") or ""),
                    "author": str(record.get("author") or ""),
                    "license": str(record.get("license") or ""),
                }
            )
        result.append(item)
    return result, len(records) > MAX_MODULES


def _registry_fingerprint(env) -> str:
    models = getattr(getattr(env, "registry", None), "models", {}) or {}
    names = sorted(str(name) for name in models)
    return canonical_fingerprint(
        {"models": names[:4096], "model_count": len(names)}
    )


def collect_runtime_inventory(
    context: CapabilityContext,
) -> tuple[dict[str, JsonValue], str]:
    """Collect a sanitized installation snapshot under the effective user."""

    env = _env(context)
    technical = _is_technical(context)
    modules, truncated = _module_payload(env, technical=technical)
    payload: dict[str, JsonValue] = {
        "odoo": _release_payload(),
        "database_identity": _database_identity(env),
        "module_count_returned": len(modules),
        "modules_truncated": truncated,
        "installed_modules": modules,
        "registry_fingerprint": _registry_fingerprint(env),
        "visibility": "technical" if technical else "user",
    }
    # Absolute roots, credentials, host commands/processes and mutable business
    # snapshots are intentionally absent. No retired HTTP/machine-auth inventory
    # service is consulted by this provider.
    return payload, canonical_fingerprint(payload)


def _build_ref(
    context: CapabilityContext,
    *,
    fingerprint: str,
    freshness: EvidenceFreshness = EvidenceFreshness.CURRENT,
) -> EvidenceRef:
    technical = _is_technical(context)
    return EvidenceRef(
        evidence_id="runtime:installation:current",
        kind=EvidenceKind.RUNTIME,
        provider_id=PROVIDER_ID,
        locator=EvidenceLocator(
            provider_id=PROVIDER_ID,
            source_id=SOURCE_ID,
            key="current_inventory",
        ),
        title="Current Odoo installation inventory",
        provenance="Effective Odoo registry and installed module records",
        fingerprint=fingerprint,
        captured_at=datetime.now(UTC),
        freshness=freshness,
        trust=EvidenceTrust.HOST_FACT,
        access_scope=EvidenceAccessScope.bind(
            context,
            group_xmlids=("base.group_system",) if technical else (),
        ),
        citation={"source_type": "odoo_runtime", "source_id": SOURCE_ID},
        metadata={
            "mutable_business_data": False,
            "logical_locator_only": True,
            "visibility": "technical" if technical else "user",
        },
    )


def _search(
    context: CapabilityContext,
    request: EvidenceSearchRequest,
) -> EvidenceSearchResult:
    if request.kinds and not {
        EvidenceKind.RUNTIME,
        EvidenceKind.CONFIGURATION,
    }.intersection(request.kinds):
        return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
    query = request.query.casefold()
    if not request.kinds and not any(
        token in query
        for token in (
            "odoo",
            "módulo",
            "modulo",
            "module",
            "instal",
            "version",
            "registry",
            "configur",
            "entorno",
            "environment",
        )
    ):
        return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
    _payload, fingerprint = collect_runtime_inventory(context)
    return EvidenceSearchResult(
        provider_id=PROVIDER_ID,
        refs=(_build_ref(context, fingerprint=fingerprint),),
    )


def _fetch(context: CapabilityContext, requested: EvidenceRef) -> EvidenceItem:
    if requested.locator.source_id != SOURCE_ID or requested.locator.key != "current_inventory":
        raise CapabilityError("runtime_inventory_locator_invalid")
    if not requested.access_scope.allows(context):
        raise CapabilityError("evidence_access_denied")
    payload, fingerprint = collect_runtime_inventory(context)
    freshness = (
        EvidenceFreshness.CURRENT
        if fingerprint == requested.fingerprint
        else EvidenceFreshness.STALE
    )
    ref = _build_ref(context, fingerprint=fingerprint, freshness=freshness)
    if freshness == EvidenceFreshness.STALE:
        payload = {
            **payload,
            "requested_fingerprint": requested.fingerprint,
            "freshness_note": (
                "The installation changed since this reference was collected."
            ),
        }
    return EvidenceItem(
        ref=ref,
        excerpt=(
            "Odoo installation inventory: "
            f"{payload['module_count_returned']} installed modules returned; "
            f"fingerprint {fingerprint[:12]}."
        ),
        data=payload,
    )


def build_runtime_inventory_evidence_provider() -> EvidenceProvider:
    return EvidenceProvider(
        provider_id=PROVIDER_ID,
        version="1",
        kinds=(EvidenceKind.RUNTIME, EvidenceKind.CONFIGURATION),
        search=_search,
        fetch=_fetch,
        optional=True,
        default_enabled=True,
        max_results=2,
        max_excerpt_bytes=8 * 1024,
        max_total_bytes=96 * 1024,
        metadata={
            "namespace_owner": "core",
            "source": SOURCE_ID,
            "effective_user_env": True,
            "su": False,
        },
    )


__all__ = [
    "MAX_MODULES",
    "PROVIDER_ID",
    "SOURCE_ID",
    "build_runtime_inventory_evidence_provider",
    "collect_runtime_inventory",
]
