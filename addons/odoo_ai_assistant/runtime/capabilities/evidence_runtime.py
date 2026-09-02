"""Provider-neutral Evidence collection and working-context projection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .contracts import CapabilityContext, CapabilityError, JsonValue
from .evidence import (
    EvidenceItem,
    EvidenceLedger,
    EvidenceLedgerSnapshot,
    EvidenceProviderCatalog,
    EvidenceProviderStatus,
    EvidenceRef,
    EvidenceRoutingPolicy,
    EvidenceSearchRequest,
)

DEFAULT_MAX_FETCHES_PER_DECISION = 4


def _error_code(exc: BaseException, fallback: str) -> str:
    if isinstance(exc, CapabilityError) and exc.args:
        return str(exc.args[0])[:160]
    return fallback


@dataclass(frozen=True, slots=True)
class EvidenceFetchFailure:
    evidence_id: str
    provider_id: str
    error_code: str

    def to_host_metadata(self) -> dict[str, JsonValue]:
        return {
            "evidence_id": self.evidence_id,
            "provider_id": self.provider_id,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class EvidenceWorkingContext:
    """One bounded collection result for a provider decision."""

    provider_ids: tuple[str, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()
    items: tuple[EvidenceItem, ...] = ()
    provider_statuses: tuple[EvidenceProviderStatus, ...] = ()
    fetch_failures: tuple[EvidenceFetchFailure, ...] = ()
    ledger: EvidenceLedgerSnapshot = field(default_factory=EvidenceLedgerSnapshot)

    def host_contract(self) -> dict[str, JsonValue]:
        """Sanitized structure/status only; never retrieved content."""

        return {
            "source": "evidence_contract",
            "provider_ids": list(self.provider_ids),
            "reference_ids": [item.evidence_id for item in self.refs],
            "provider_statuses": [
                {
                    "provider_id": status.provider_id,
                    "state": status.state,
                    "kinds": [kind.value for kind in status.kinds],
                    "error_code": status.error_code,
                }
                for status in self.provider_statuses
            ],
            "fetch_failures": [
                failure.to_host_metadata() for failure in self.fetch_failures
            ],
            "ledger_revision": self.ledger.revision,
        }

    def untrusted_data(self) -> tuple[dict[str, JsonValue], ...]:
        return tuple(item.to_untrusted_projection() for item in self.items)


class AssistantEvidenceDecisionEngine:
    """Collect bounded Evidence for one host-controlled decision step.

    The engine owns no model, transport, capability or effect authority. It only
    routes/searches/fetches Evidence and maintains the trust partition/ledger.
    """

    def __init__(
        self,
        catalog: EvidenceProviderCatalog,
        *,
        routing_policy: EvidenceRoutingPolicy | None = None,
        max_fetches_per_decision: int = DEFAULT_MAX_FETCHES_PER_DECISION,
    ) -> None:
        if not 0 <= max_fetches_per_decision <= 16:
            raise CapabilityError("evidence_fetch_limit_invalid")
        self._catalog = catalog
        self._routing_policy = routing_policy or EvidenceRoutingPolicy()
        self._max_fetches = max_fetches_per_decision

    def collect(
        self,
        context: CapabilityContext,
        request: EvidenceSearchRequest,
        *,
        ledger: EvidenceLedger | None = None,
        fetch_reference_ids: Iterable[str] = (),
    ) -> EvidenceWorkingContext:
        active_ledger = ledger or EvidenceLedger()
        batch = self._catalog.search(
            context,
            request,
            routing_policy=self._routing_policy,
        )
        for ref in batch.refs:
            active_ledger.register(ref, retain_excerpt=False)

        requested_ids = tuple(
            dict.fromkeys(str(item) for item in fetch_reference_ids)
        )
        refs_by_id = {item.evidence_id: item for item in batch.refs}
        selected_refs = (
            tuple(refs_by_id[item] for item in requested_ids if item in refs_by_id)
            if requested_ids
            else batch.refs
        )[: self._max_fetches]

        items: list[EvidenceItem] = []
        failures: list[EvidenceFetchFailure] = []
        for ref in selected_refs:
            try:
                item = self._catalog.fetch(context, ref)
                active_ledger.register(item)
                items.append(item)
            except Exception as exc:
                code = _error_code(exc, "evidence_fetch_failed")
                if code.startswith("required_evidence_provider_"):
                    raise CapabilityError(code) from exc
                failures.append(
                    EvidenceFetchFailure(
                        evidence_id=ref.evidence_id,
                        provider_id=ref.provider_id,
                        error_code=code,
                    )
                )

        return EvidenceWorkingContext(
            provider_ids=tuple(
                status.provider_id
                for status in batch.statuses
                if status.state == "available"
            ),
            refs=batch.refs,
            items=tuple(items),
            provider_statuses=batch.statuses,
            fetch_failures=tuple(failures),
            ledger=active_ledger.snapshot(),
        )


__all__ = [
    "DEFAULT_MAX_FETCHES_PER_DECISION",
    "AssistantEvidenceDecisionEngine",
    "EvidenceFetchFailure",
    "EvidenceWorkingContext",
]
