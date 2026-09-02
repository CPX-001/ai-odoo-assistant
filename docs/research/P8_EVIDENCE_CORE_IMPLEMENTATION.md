# P8 evidence core implementation checkpoint

Date: 2026-09-02  
State: `IMPLEMENTED / FOCUSED VALIDATION PENDING`

## Scope

This checkpoint implements the coherent P8.0 hardening plus P8.1/P8.2 foundation
prepared after P7. It follows the confirmed product decisions in the adapted
architecture packet without claiming later P8 source/log/observability functionality
complete.

## Implemented

### Supported-path cleanup

- Removed the obsolete GitHub Actions workflow that tested the retired sidecar and
  installer lineage.
- Removed the `auth="none"` internal inventory callback and its controller import.
- Kept installation inventory as an in-process Evidence source.
- Added a regression test that rejects any Assistant controller using `auth="none"`.

### Evidence contracts

Added `runtime/capabilities/evidence.py` with:

```text
EvidenceKind / EvidenceTrust / EvidenceFreshness
EvidenceAccessScope
EvidenceLocator
EvidenceRef / EvidenceItem
EvidenceSearchRequest / EvidenceSearchResult
EvidenceProvider / EvidenceProviderStatus
EvidenceProviderCatalog
EvidenceRoutingPolicy
EvidenceLedger / EvidenceLedgerSnapshot
```

Contracts enforce logical locators, finite/canonical JSON, deep immutability,
secret redaction, byte/count limits, provenance, access binding, freshness and
explicit conflict groups. Evidence content is projected only as untrusted data.

The initial ledger retains at most 64 refs, 16 excerpts, 8 KiB per excerpt and
64 KiB total.

### P7 extension hardening

- Added `CAPABILITY_PROVIDER_API_VERSION = "1"`.
- Added reserved core namespaces and immutable provider metadata.
- Added `evidence_providers` to `CapabilityProvider` while preserving existing P7
  positional field order.
- Composed Evidence only from providers accepted by the executable registry.
- Isolated optional Evidence guard/search failures and failed required providers
  closed.
- Fed Skills' existing Evidence selectors from the effective available catalog.
- Reused the existing manifest/extension seam rather than adding another registry.

### Runtime inventory provider

Added `assistant.runtime_inventory`, which returns a bounded, sanitized projection
of Odoo release information, hashed database identity, installed modules and a
registry fingerprint under the effective user Environment. It exposes neither
absolute addon roots nor credentials, commands or mutable business snapshots.
Fingerprint mismatch is returned as explicit stale Evidence.

### Architecture/source policy

Added:

```text
docs/EVIDENCE_ARCHITECTURE.md
docs/OBSERVABILITY_ARCHITECTURE.md
docs/CONTEXT_SOURCE_POLICY.md
docs/TURN_LIFECYCLE_COMPOSITION.md
docs/adr/ADR-022-evidence-core-and-ledger.md
docs/adr/ADR-023-host-owned-observability.md
docs/adr/ADR-024-technical-host-privilege-broker.md
addons/odoo_ai_assistant/runtime/context_source_policy.json
```

ADR-024 is deliberately proposed only; this checkpoint creates no privileged
helper, shell, repository acquisition or host operation.

## Tests prepared

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/addon/test_phase8_runtime_evidence.py
```

Coverage targets:

- exact bounded shape, canonicalization, deep immutability and secret redaction;
- provider API version and reserved namespaces;
- optional guard/search failure isolation;
- search/fetch access recheck;
- ledger dedup, restore, identity conflict and overflow transactionality;
- effective Evidence provider IDs and question-sensitive routing;
- no `auth="none"` route and no obsolete workflow;
- live Odoo inventory grounding and stale fingerprint behavior.

## Validation truth

This checkpoint was authored through the GitHub connector. That interface can read
and write the repository but does not execute the Odoo/Codex/browser test
environment. Therefore:

```text
focused dependency-light tests    NOT EXECUTED in this checkpoint
focused Odoo tests                 NOT EXECUTED in this checkpoint
real provider/browser gates        NOT EXECUTED
P8 acceptance                      NOT CLAIMED
```

The next execution environment must run the focused tests above plus directly
affected existing P7 extension/boundary tests, repair failures at their owning
layer and record exact evidence. A full regression is not implied unless the active
runbook is updated to require it.

## Explicitly deferred

- complete live model-driven search/fetch orchestration and citation UX;
- runtime/schema/security/navigation providers beyond inventory;
- source/XML/module-doc index and validators;
- correlated log provider and automatic diagnosis;
- full observability spans/self-inspection capabilities/secret UI;
- company Knowledge/RAG;
- domain addon split and `auto_install` validation;
- repository/module acquisition and Technical host broker.

These belong to later P8/P9/P10 slices and must not be inferred as implemented from
this foundation.

## Next action

Run the focused P8 dependency-light and Odoo tests in a checkout with Odoo 18,
repair any integration/contract regressions, then connect bounded Evidence
search/fetch into the live provider-neutral decision path and execute the six P8
real gates before acceptance.
