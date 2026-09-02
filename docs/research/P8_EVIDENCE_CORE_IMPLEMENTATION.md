# P8 evidence core implementation checkpoint

Date: 2026-09-02  
State: `IMPLEMENTED / FOCUSED VALIDATION PENDING`

This checkpoint applies and reconciles the P8 changeset specification against the
current `main` after accepted P7. Newer main behavior is preserved; only missing or
contradictory P8.0 hardening and P8.1/P8.2 Evidence foundation behavior is changed.
No unexecuted test or real gate is claimed as PASS.

## Implemented

### Supported-path cleanup

- Removed the obsolete GitHub Actions workflow that validated retired sidecar/installer lineage.
- Removed the `auth="none"` internal inventory callback and controller import.
- Removed the addon-local `security/machine_auth.py` primitive and its exports.
- Removed the residual supported `services/instance_inventory.py` compatibility layer.
- Installation inventory is now owned directly by the in-process `assistant.runtime_inventory` Evidence provider.
- Updated addon/unit boundary tests so the supported executable addon rejects the retired callback, machine-auth and inventory-service paths.
- Historical `service/`/installer machine-secret references remain history only and are excluded from normal current context.

### Evidence contracts

`runtime/capabilities/evidence.py` provides:

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

Deep immutable JSON now uses `FrozenDict` / `FrozenList` wrappers so callers that
legitimately depend on `isinstance(value, dict)` or `isinstance(value, list)` remain
compatible while mutation still raises. Canonical/thaw helpers remain host-owned.
The same immutable contract is applied to capability schemas/results/context metadata,
provider metadata, Skill metadata and ContextProvider metadata/results.

The initial ledger retains at most 64 refs, 16 excerpts, 8 KiB per excerpt and 64 KiB
total.

### Provider hardening

- `CAPABILITY_PROVIDER_API_VERSION = "1"` remains the explicit extension API.
- Reserved core namespaces are enforced for provider and contributed resource IDs.
- API mismatch, loader failure, collisions, dependency/version errors and dependency cycles are attributed at provider boundaries.
- An optional broken provider no longer removes unrelated healthy optional providers.
- Required providers still fail closed.
- Capability group checks and guards fail closed on exceptions instead of leaking provider/user internals.
- Provider status exposes sanitized `provider_id`, `version`, `api_version`, state, optionality and capability/Skill/Context/Evidence counts without raw exceptions.
- `evidence_providers` remains part of `CapabilityProvider`; there is no parallel extension registry.

### Skills and product profiles

Skills consume the effective available Evidence-provider IDs through the existing
`evidence_provider_selectors` seam. They may guide retrieval but cannot create
execution authority.

Public product behavior is exactly:

```text
user
technical
```

Historical internal `business`/`developer` access-profile names remain only as a
compatibility seam and are normalized before public manifest projection. They do not
create extra product personas. The future Technical/host broker remains an execution
boundary, not a third human profile.

### Runtime inventory provider

`assistant.runtime_inventory` returns a bounded sanitized projection of Odoo release
information, hashed database identity, installed modules and registry fingerprint
under the effective Odoo Environment. It exposes neither absolute addon roots nor
raw database names, credentials, commands or mutable business snapshots. Fingerprint
mismatch is returned as explicit stale Evidence.

The provider no longer imports or calls the retired addon inventory service. This
removes the former raw database/addon-root payload from the supported P8 path.

### Live provider-neutral Evidence projection

The existing `AssistantExtensionDecisionEngine` now connects the Evidence foundation
to the live provider-neutral decision seam without creating an Evidence-specific
agent runtime:

```text
message
 -> question-sensitive EvidenceRoutingPolicy
 -> effective EvidenceProviderCatalog
 -> bounded search
 -> bounded fetch (host max per decision)
 -> EvidenceLedger
 -> host structural metadata + untrusted Evidence working items
 -> current reasoning provider
```

Generic/social turns do not perform automatic Evidence retrieval. Installation,
how-to, configuration and diagnosis-shaped questions can retrieve bounded Evidence.
The current Codex adapter only teaches the existing trust partition how to serialize
that provider-neutral structure:

- `host_assistant_evidence` contains sanitized host-owned provider/ref/status metadata;
- `assistant_evidence` remains untrusted data, including any prompt-injection text;
- Evidence never grants capabilities, policy, approval or permissions;
- provenance/freshness/trust/citation metadata may ground answers but does not become authority.

`EffectiveAssistantManifest.evidence_provider_ids` remains the single manifest seam.

### Ledger durability decision for this checkpoint

The live wrapper owns one bounded turn-scoped `EvidenceLedger`. Its schema is
serializable/versioned and ready for durable storage, but this checkpoint does not
claim reconnect restoration. The changeset explicitly permits an ephemeral snapshot
when reconnect recovery is not yet a checkpoint requirement. Durable transcript
restoration must reuse the existing Odoo working-transcript infrastructure rather
than create another database/service.

### Architecture/source policy

Current documentation treats P7 as accepted and P8 as implemented-with-validation-debt.
Relevant current records include:

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

ADR-024 remains **Proposed** only. This checkpoint creates no privileged helper,
shell, repository acquisition or unrestricted host operation.

## Tests prepared/updated

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/unit/test_phase8_product_profiles.py
tests/unit/test_capability_provider_extensions.py
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_live_extension_context.py
tests/addon/test_phase8_runtime_evidence.py
tests/addon/test_addon_boundaries.py
addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
```

Coverage targets now include:

- exact bounded shape, canonicalization, deep immutability and dict/list compatibility;
- secret redaction;
- provider API mismatch and reserved provider/resource namespaces;
- fine-grained optional loader/dependency/cycle/guard/search failure isolation;
- search/fetch access recheck;
- ledger dedup, restore, identity conflict and overflow transactionality;
- effective Evidence provider IDs and Skill selectors;
- question-sensitive routing with no generic pre-retrieval;
- public `user` / `technical` manifest projection;
- live Evidence host/untrusted trust partition, including indirect prompt-injection text;
- no supported `auth="none"` callback, addon machine-auth primitive or inventory service;
- live Odoo inventory grounding and stale-fingerprint behavior;
- existing plan tests adapted to immutable `CapabilityContext` metadata rather than mutating host contracts after capture.

## Validation truth

These changes were authored/published through the GitHub connector. That interface
can read/write the repository but does not execute the Odoo/Codex/browser test
environment. Therefore:

```text
focused dependency-light tests    NOT EXECUTED in this checkpoint
focused Odoo tests                 NOT EXECUTED in this checkpoint
P8 real gates                      NOT EXECUTED
P8 acceptance                      NOT CLAIMED
```

Do not infer PASS from source inspection or the existence of tests.

## Explicitly deferred

- durable reconnect restoration of the Evidence ledger in the Odoo working transcript;
- richer end-user citation rendering/navigation;
- runtime/schema/security/navigation providers beyond inventory;
- source/XML/module-doc index and validators;
- correlated log provider and automatic diagnosis;
- full observability spans/self-inspection capabilities;
- secret masked/copy/reveal UI;
- company Knowledge/RAG;
- domain addon split and `auto_install` validation;
- repository/module acquisition and Technical host broker.

These belong to later P8/P9/P10 slices and are not falsely marked complete by this
foundation checkpoint.

## Next action

Run the focused P8 dependency-light and Odoo tests in a checkout with Odoo 18,
including the directly affected P7 extension and canonical-plan boundaries. Repair
failures at their owning layer and record exact evidence. Only then continue toward
durable ledger reconnect/citation UX and the six P8 real gates.

A full regression is not implied unless the active runbook/cursor is updated to
require it.
