# Evidence architecture

Status: P8 foundation implemented; focused and real validation pending.

## Purpose

Evidence gives the Assistant installation-specific facts without turning retrieved
content into authority. It unifies runtime, schema, configuration, source, XML,
logs, documents, web and business-record references behind one bounded contract.
It is broader than vector RAG: different facts continue to use the source best
suited to them.

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

## Authority boundary

Evidence is data. It cannot:

- create or enable a `CapabilityDefinition`;
- change ACLs, record rules, companies or field access;
- waive policy, approval, budgets or verification;
- grant Technical/host privileges;
- override host/Skill instructions;
- become an executable filesystem path, method name, command or SQL fragment.

The model may ask for another source. The host may require a local/current source
for installation-specific or safety-critical claims.

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

### Access and freshness

Access scope binds the ref to the collecting user/companies/groups/source ACL.
The same scope is checked again on fetch. A changed fingerprint produces explicit
`stale` evidence. `missing` and `revoked` refs are never silently accepted.

### Bounds and immutability

Contracts reject non-finite JSON, excessive depth/items/keys/bytes and arbitrary
absolute/traversal locators. Caller-owned mappings/sequences are copied and deeply
frozen. Canonical JSON supports deterministic fingerprints.

The initial ledger limits are:

```text
64 references per turn
16 retained excerpts
8 KiB per retained excerpt
64 KiB serialized ledger
```

Corpora remain in their providers. The ledger only persists refs and selected,
bounded excerpts required for reconnect/continuation.

## Provider composition

`CapabilityProvider` API v1 may contribute `evidence_providers`. Evidence is
composed only when the owning capability provider was accepted by the executable
registry. Optional failures are isolated; required providers fail closed.

The existing `SkillDefinition.evidence_provider_selectors` seam receives IDs from
the effective available Evidence catalog, not from arbitrary prompt text.
`EffectiveAssistantManifest.evidence_provider_ids` remains the single manifest
projection seam; P8 does not create a second manifest or tool registry.

## Routing policy

Routing prioritizes source classes; it does not classify the whole turn into a
rigid GENERAL/QUERY/HOW_TO/ACTION route.

| Question class | Initial evidence order |
|---|---|
| Current business state | live ORM, runtime/schema |
| Installation/module behavior | runtime, configuration, docs, source/XML |
| Standard how-to | versioned docs, then local verification |
| Error diagnosis | diagnostic/turn trace, logs, runtime, source/XML |
| Company policy | governed document/Knowledge providers |
| Repository/module preflight | web metadata, manifest/docs, bounded source scan |
| Current external fact | web when deployment policy permits |

Providers and future Skills can refine selection without bypassing host policy.

## First provider: installation inventory

`assistant.runtime_inventory` exposes a sanitized Odoo version/edition projection,
hashed database identity, installed modules, registry fingerprint and visibility
profile. It uses the effective Odoo Environment and does not expose absolute addon
roots, credentials, arbitrary scripts or mutable business snapshots.

The former sidecar callback was removed. Existing internal instance-inventory code
may be reused only as an in-process source and its raw legacy payload is not
projected automatically.

## Planned providers

The next P8 slices add:

1. runtime/schema/config/security/navigation evidence;
2. bounded source/XML/module documentation and deterministic validators;
3. correlated logs/tracebacks;
4. host-owned observability/self-inspection;
5. company Knowledge and uploaded sources in P9.

FTS/lexical search should precede vector search when exact identifiers and Odoo
structure are more reliable. Embeddings are an additional provider strategy, not
the definition of Evidence.

## Validation

Prepared deterministic/Odoo tests cover shape, immutability, secret redaction,
access recheck, optional-provider isolation, routing, ledger restore/overflow and
runtime inventory freshness. The six P8 real gates remain HARD and are not PASS
until executed in the prescribed real environment.
