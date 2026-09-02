# ADR-022 — Provider-neutral Evidence core and bounded ledger

Status: Accepted; P8 foundation implementation focused validation pending  
Date: 2026-09-02

## Context

The Assistant must explain the behavior of the effective Odoo installation using
runtime, schema, configuration, source, XML, logs, documents and future web/
Knowledge sources. Treating every source as generic vector RAG would lose
structure, freshness, access and causal provenance. Injecting all content into a
prompt would also create an unbounded prompt-injection and privacy surface.

P7 already established one capability registry, installed-addon providers, Skills,
JIT context and the manifest seam `evidence_provider_ids`. P8 must extend that
framework instead of creating another tool registry or runtime.

## Decision

Introduce provider-neutral Evidence contracts around, not inside, executable
`CapabilityDefinition`:

```text
CapabilityProvider
 -> CapabilityDefinition[]
 -> SkillDefinition[]
 -> ContextProvider[]
 -> EvidenceProvider[]
```

`EvidenceProvider.search` returns bounded `EvidenceRef` metadata. `fetch` resolves a
logical locator and rechecks provider identity, effective access scope, fingerprint,
freshness and output bounds.

Evidence has explicit kind, trust and freshness. Content is always projected as
untrusted data. Host-owned metadata may describe IDs/kinds/statuses, but retrieved
content never becomes a Skill/system instruction or execution authority.

Persist a bounded Odoo-owned Evidence ledger per turn when continuation/audit needs
it. The initial maximum is 64 refs, 16 excerpts, 8 KiB per excerpt and 64 KiB total.
Corpora remain in their owning provider.

Reuse `EffectiveAssistantManifest.evidence_provider_ids`; do not create a second
manifest. Skills select from the effective available Evidence catalog.

## Required properties

- Effective user/company/group/source scope is checked on collect and fetch.
- Changed fingerprints are explicit `stale`; missing/revoked sources are not
  silently accepted.
- Conflicting sources remain distinguishable through provider/provenance/conflict
  group.
- Locators are logical host-created values, never arbitrary model-authored paths.
- JSON is finite, bounded, canonicalized and deeply frozen.
- Secrets, raw prompts, private reasoning and unsanitized logs are excluded/redacted.
- Optional provider failure is isolated; required provider failure closes safely.
- Evidence cannot affect capability availability, policy, approval or profile.

## First implementation

The first built-in provider is `assistant.runtime_inventory`, exposing a sanitized
Odoo installation/module/registry fingerprint from the effective Environment. The
retired unauthenticated sidecar inventory callback is removed; inventory is an
in-process Evidence source.

## Consequences

Positive:

- installation-specific answers can cite current facts;
- future source/XML/log/Knowledge/web providers share access/freshness semantics;
- no vector store or external service is required for P8 foundation;
- reconnect/audit does not duplicate entire corpora.

Costs:

- providers must implement stable logical locators and freshness;
- the host must maintain byte/count/time budgets and source-specific ACLs;
- real product evals are required to tune routing and context size.

## Rejected alternatives

- Vector-search-only RAG for every source.
- A second registry of retrieval tools.
- Persisting raw provider search/fetch payloads per turn.
- Passing repository paths, SQL, shell or unrestricted Odoo methods to the model.
- Treating documents/source/log text as trusted instructions.

## Validation

Dependency-light and Odoo tests are added with the implementation. Their presence
is not PASS evidence. The six P8 real gates remain HARD until executed and recorded
according to the active runbook.
