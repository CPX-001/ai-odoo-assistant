# Evidence architecture

Status: P8 foundation and first live provider-neutral projection implemented; focused and real validation pending.

## Purpose

Evidence gives the Assistant installation-specific facts without turning retrieved
content into authority. It unifies runtime, schema, configuration, source, XML,
logs, documents, web and business-record references behind one bounded contract.
It is broader than vector RAG: each fact continues to use the source best suited to
it.

```text
question / current turn
  -> EvidenceRoutingPolicy
  -> effective EvidenceProviderCatalog
  -> search: bounded EvidenceRef[]
  -> fetch: access + locator + freshness recheck
  -> selected EvidenceItem[]
  -> bounded EvidenceLedger
  -> provider-neutral untrusted working-context projection
```

The current live `AssistantExtensionDecisionEngine` uses this path only for questions
that the host routing policy considers evidence-relevant. Generic/social turns do not
receive a compulsory retrieval dump.

## Authority boundary

Evidence is data. It cannot:

- create or enable a `CapabilityDefinition`;
- change ACLs, record rules, companies or field access;
- waive policy, approval, budgets or verification;
- grant Technical/host privileges;
- override host/Skill instructions;
- become an executable filesystem path, method name, command or SQL fragment.

The model may reason over Evidence or ask for another source. The host remains the
only component that chooses available providers, validates locators/access/freshness
and executes capabilities.

## Contracts

The implementation is in
`addons/odoo_ai_assistant/runtime/capabilities/evidence.py`.

### `EvidenceRef`

A ref contains a stable ID, kind, provider, logical locator, title, provenance,
fingerprint, capture time, freshness, trust, access scope, citation metadata and
an optional conflict group. Search returns refs rather than dumping a corpus.

### `EvidenceItem`

Fetch resolves one ref into a bounded excerpt and JSON data. It is projected as:

```text
source = evidence
trust_boundary = untrusted_data
reference = host-owned metadata
excerpt/data = untrusted content
```

The Codex adapter does not get a special Evidence authority path. It receives only
host structural metadata separately from untrusted retrieved content at the existing
provider-neutral trust partition.

### Access and freshness

Access scope binds the ref to the collecting user, companies, groups and source
ACL. The same scope is checked again on fetch. A changed fingerprint produces
explicit `stale` evidence. `missing` and `revoked` refs are never silently accepted.

### Bounds and immutability

Contracts reject non-finite JSON, excessive depth/items/keys/bytes and arbitrary
absolute/traversal locators. Caller-owned mappings/sequences are copied and deeply
frozen. `FrozenDict` / `FrozenList` preserve normal `dict` / `list` type checks while
rejecting mutation. Canonical JSON and explicit thawing support deterministic
fingerprints and transport serialization.

The initial ledger limits are:

```text
64 references per turn
16 retained excerpts
8 KiB per retained excerpt
64 KiB serialized ledger
```

Corpora remain in their providers. The live wrapper currently retains the ledger for
the turn and the snapshot format is serializable/versioned. Durable reconnect
restoration is intentionally not claimed yet; when implemented it must reuse the
existing Odoo working-transcript persistence rather than introduce another store.

## Provider composition

`CapabilityProvider` API v1 may contribute `evidence_providers`. Evidence is
composed only when the owning capability provider was accepted by the executable
registry. Provider/resource namespaces are validated at the host boundary.

Optional API, loader, collision, dependency, cycle, guard and Evidence failures are
isolated to the attributable provider subset where possible; required providers fail
closed. Raw exceptions are not part of provider introspection.

The existing `SkillDefinition.evidence_provider_selectors` seam receives IDs from
the effective available Evidence catalog, not prompt text.
`EffectiveAssistantManifest.evidence_provider_ids` remains the single manifest
projection seam; P8 does not create a second manifest or tool registry.

## Routing policy

Routing prioritizes source classes; it does not classify the whole turn into a
rigid GENERAL/QUERY/HOW_TO/ACTION route. The initial policy also has a retrieval
threshold: a generic turn can legitimately select no Evidence provider.

| Question class | Initial evidence order |
|---|---|
| Current business state | live ORM, runtime/schema when needed |
| Installation/module behavior | runtime, configuration, docs, source/XML |
| Standard how-to | versioned docs, then local verification |
| Error diagnosis | diagnostic/turn trace, logs, runtime, source/XML |
| Company policy | governed document/Knowledge providers |
| Repository/module preflight | web metadata, manifest/docs, bounded source scan |
| Current external fact | web when deployment policy permits |

Only the runtime/installation provider exists in this checkpoint; the table describes
routing direction for later providers, not capabilities falsely claimed as present.

## First provider: installation inventory

`assistant.runtime_inventory` exposes a sanitized Odoo version/edition projection,
hashed database identity, installed modules, registry fingerprint and visibility
profile. It is an in-process Evidence provider and does not expose absolute addon
roots, raw database names, credentials, arbitrary scripts or mutable business
snapshots.

The former sidecar callback, addon machine-auth primitive and residual
`services/instance_inventory.py` compatibility path have been removed from the
supported addon. Historical sidecar code remains historical evidence only.

## Live projection

For a relevant model decision the current path is:

```text
AssistantExtensionDecisionEngine
  -> active Evidence provider IDs
  -> EvidenceRoutingPolicy.should_retrieve
  -> AssistantEvidenceDecisionEngine.collect
  -> EvidenceProviderCatalog.search/fetch
  -> bounded EvidenceLedger
  -> host_assistant_evidence     # structure/status only
  -> assistant_evidence          # untrusted reference/excerpt/data
  -> reasoning provider
```

The host search request is bounded and the decision engine limits fetches per model
decision. Evidence prompt injection stays in the untrusted partition and cannot
change the effective capability catalog.

## Planned providers

Later P8/P9 slices may add:

1. runtime/schema/config/security/navigation evidence;
2. bounded source/XML/module documentation and deterministic validators;
3. correlated logs/tracebacks;
4. host-owned observability/self-inspection;
5. company Knowledge and uploaded sources.

FTS/lexical search should precede vector search when exact identifiers and Odoo
structure are more reliable. Embeddings are an additional provider strategy, not
the definition of Evidence.

## Validation

Prepared deterministic/Odoo tests cover shape, dict/list-compatible deep
immutability, secret redaction, access recheck, fine-grained optional-provider
isolation, routing, Skill selectors, live host/untrusted projection, ledger
restore/overflow and runtime inventory freshness. The focused tests and six P8 real
gates remain NOT EXECUTED until run in the prescribed environment.
