# P8 evidence core implementation checkpoint

Date: 2026-09-02  
State: `IMPLEMENTED / FOCUSED VALIDATION PENDING`

This checkpoint implements the coherent P8.0 hardening plus P8.1/P8.2 Evidence
foundation after accepted P7. It follows the confirmed product decisions in the
adapted architecture packet without claiming later P8 source/log/observability work
complete.

## Implemented

### Supported-path cleanup

- Removed the obsolete GitHub Actions workflow that validated retired sidecar/installer lineage.
- Removed the `auth="none"` internal inventory callback and controller import.
- Removed the now-unreferenced addon-local `security/machine_auth.py` primitive and its exports.
- Updated addon boundary tests so the supported executable addon rejects the retired callback/machine-auth path.
- Kept installation inventory as an in-process Evidence source.
- Historical `service/`/installer machine-secret references remain history only and are excluded from normal current context.

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

Contracts enforce logical locators, finite/canonical JSON, deep immutability, secret
redaction, byte/count limits, provenance, access binding, freshness and explicit
conflict groups. Evidence content is projected only as untrusted data.

The initial ledger retains at most 64 refs, 16 excerpts, 8 KiB per excerpt and 64 KiB
total.

### P7 extension hardening

- Added `CAPABILITY_PROVIDER_API_VERSION = "1"`.
- Added reserved core namespaces and immutable provider metadata.
- Added `evidence_providers` to `CapabilityProvider` while preserving accepted P7 composition semantics.
- Composed Evidence only from providers accepted by the executable extension boundary.
- Isolated optional Evidence guard/search failures and failed required providers closed.
- Fed Skills' existing Evidence selectors from the effective available catalog.
- Reused the existing `EffectiveAssistantManifest.evidence_provider_ids` seam instead of adding a second manifest/registry.

### Product profiles

Public product behavior now maps to exactly:

```text
User / non-technical
Technical
```

Historical internal `business`/`developer`-style values may remain for compatibility
but do not create extra product personas. The future Technical/host broker remains an
execution boundary, not a third human profile.

### Runtime inventory provider

Added `assistant.runtime_inventory`, which returns a bounded sanitized projection of
Odoo release information, hashed database identity, installed modules and registry
fingerprint under the effective user Environment. It exposes neither absolute addon
roots nor credentials, commands or mutable business snapshots. Fingerprint mismatch
is returned as explicit stale Evidence.

### Architecture/source policy

Current documentation now treats P7 as accepted and P8 as implemented-with-validation-debt.
The current reading path is:

```text
README.md
 -> docs/CURRENT_STATE.md
 -> docs/ARCHITECTURE.md
 -> docs/PRODUCT_VISION.md
 -> docs/CAPABILITY_FRAMEWORK.md
 -> docs/EVIDENCE_ARCHITECTURE.md
 -> docs/OBSERVABILITY_ARCHITECTURE.md
 -> docs/research/EXECUTION_STATE.md
```

Added/maintained:

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

ADR-024 is deliberately **Proposed** only. This checkpoint creates no privileged
helper, shell, repository acquisition or host operation.

## Confirmed product decisions represented

- one customer-facing Odoo AI Assistant product, even if internal domain/link addons appear later;
- only User and Technical human product profiles;
- approval/autonomy is policy-driven, with no redundant confirmation requirement for every effect;
- full-control never grants more Odoo authority than the effective user;
- arbitrary repositories may be candidates after bounded web/repo preflight; allowlist is optional policy/trust input;
- repository/module inspection should feed chat Evidence/knowledge, not be an isolated installer workflow;
- addon-first; future host broker only for truly host-level privilege;
- user-pasted secrets do not automatically block a safe turn and must be sanitized from derived public projections;
- Assistant-presented secrets require masked/copy/reveal UX before that behavior is complete;
- no generic shell/SQL/Python/unrestricted ORM method escape hatch.

## Tests prepared

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/unit/test_phase8_product_profiles.py
tests/addon/test_phase8_runtime_evidence.py
tests/addon/test_addon_boundaries.py
```

Coverage targets include:

- exact bounded shape, canonicalization, deep immutability and secret redaction;
- provider API version and reserved namespaces;
- optional guard/search failure isolation;
- search/fetch access recheck;
- ledger dedup, restore, identity conflict and overflow transactionality;
- effective Evidence provider IDs and question-sensitive routing;
- public User/Technical profile mapping;
- no supported `auth="none"` callback or addon machine-auth primitive;
- live Odoo inventory grounding and stale-fingerprint behavior.

## Validation truth

The implementation was authored/published through the GitHub connector. That
interface can read/write the repository but does not execute the Odoo/Codex/browser
test environment. Therefore:

```text
focused dependency-light tests    NOT EXECUTED in this checkpoint
focused Odoo tests                 NOT EXECUTED in this checkpoint
real provider/browser gates        NOT EXECUTED
P8 acceptance                      NOT CLAIMED
```

Do not infer PASS from source inspection or the existence of tests.

## Explicitly deferred

- complete live model-driven Evidence search/fetch orchestration and citation UX;
- runtime/schema/security/navigation providers beyond inventory;
- source/XML/module-doc index and validators;
- correlated log provider and automatic diagnosis;
- full observability spans/self-inspection capabilities;
- secret masked/copy/reveal UI;
- company Knowledge/RAG;
- domain addon split and `auto_install` validation;
- repository/module acquisition and Technical host broker.

These belong to later P8/P9/P10 slices.

## Next action

Run the focused P8 dependency-light and Odoo tests in a checkout with Odoo 18,
including directly affected P7 extension/boundary tests. Repair failures at their
owning layer, record exact evidence, then connect bounded Evidence search/fetch to the
live provider-neutral decision path and execute the P8 real gates before acceptance.

A full regression is not implied unless the active runbook/cursor is updated to
require it.
