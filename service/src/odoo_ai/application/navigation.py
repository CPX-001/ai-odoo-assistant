"""Turn checked visible Odoo navigation into citable metadata evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    NavigationSnapshot,
)
from odoo_ai.ports.odoo import OdooGateway

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)


class NavigationServiceError(RuntimeError):
    """Sanitized failure while preparing visible navigation evidence."""

    def __init__(self, code: str, status_code: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class NavigationResult:
    """Typed visible navigation plus its checked evidence."""

    navigation: NavigationSnapshot
    evidence: Evidence


class NavigationService:
    """Obtain navigation through a gateway already bound to explicit turn authority."""

    def __init__(self, gateway: OdooGateway) -> None:
        self._gateway = gateway

    async def get(self) -> NavigationResult:
        navigation = await self._gateway.get_navigation()
        canonical = {
            "content_trust": navigation.content_trust,
            "limits": navigation.limits.model_dump(mode="json"),
            "nodes": [node.model_dump(mode="json") for node in navigation.nodes],
            "truncated": navigation.truncated,
        }
        try:
            encoded = json.dumps(
                canonical,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise NavigationServiceError("invalid_navigation") from None
        if len(encoded) > navigation.limits.max_bytes:
            raise NavigationServiceError("navigation_too_large", 413)
        fingerprint = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Visible Odoo navigation",
            summary="Visible menu paths were checked under the delegated Odoo user; labels are untrusted data.",
            payload=cast(dict[str, JsonValue], navigation.model_dump(mode="json")),
            pointer={"provider": "odoo_navigation", "root": "visible_menu_tree"},
            observed_at=navigation.captured_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=fingerprint,
        )
        return NavigationResult(navigation=navigation, evidence=evidence)
