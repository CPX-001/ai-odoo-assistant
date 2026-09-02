# Knowledge, Evidence and Retrieval

This document supersedes the retired sidecar PostgreSQL FTS Knowledge Index design.
Current code/ADRs plus `CURRENT_STATE.md` are authoritative.

## 1. Current state

P8 now has a shared embedded Evidence foundation:

```text
EvidenceKind / Trust / Freshness
EvidenceAccessScope / Locator
EvidenceRef / EvidenceItem
EvidenceSearchRequest / EvidenceSearchResult
EvidenceProvider / ProviderStatus
EvidenceProviderCatalog
EvidenceRoutingPolicy
EvidenceLedger / EvidenceLedgerSnapshot
assistant.runtime_inventory
```

The first live provider exposes bounded installation/runtime facts under the effective
Odoo Environment. General company document RAG, source/XML semantic search, correlated
logs and web Evidence are not implemented end to end yet.

The retired Assistant Service SQLAlchemy/Alembic knowledge/source implementation is
historical evidence only. Useful concepts may be reimplemented inside Odoo; its API,
database and machine-auth callback are not restored.

## 2. Product objective

Retrieval is broader than vector RAG.

```text
Evidence layer
  +-- LIVE
  |     Odoo business data
  |     runtime / module / schema / configuration
  |     security / navigation state
  |     logs / tracebacks / host diagnostics
  |
  +-- STRUCTURED / INDEXED
  |     Python / XML / module documentation
  |     company documents / attachments / Knowledge
  |     PostgreSQL lexical FTS
  |     semantic/vector index where evals justify it
  |
  +-- EXTERNAL
        web / repository metadata
        future connectors
```

A concrete installation question may combine several providers before the final
answer.

## 3. Agentic hybrid retrieval

Do not run a generic vector search before every turn.

Target pattern:

```text
small reliable BaseContext
 -> reasoning provider
     -> enough evidence? answer
     -> otherwise search an effective EvidenceProvider
     -> inspect bounded refs/items
     -> fetch/search another source when useful
     -> synthesize with provenance
```

The host may require installation-local evidence for claims that must be current,
installation-specific or safety-critical.

## 4. Evidence contract

Every retrieval mechanism normalizes to the P8 host-owned contracts rather than
leaking storage-specific response shapes into the agent loop.

Core Evidence carries:

```text
stable evidence_id
kind
provider/source identity
logical locator
title
bounded excerpt/data
provenance
fingerprint/version
captured_at
freshness
trust
access scope
optional retrieval method/score
citation metadata
optional conflict group
```

Evidence is deeply normalized, finite and bounded. Secret-looking values are redacted
from normalized mappings where possible.

Evidence is **data**, never policy. It cannot change capability availability, public
profile, approval or execution authority.

## 5. EvidenceLedger

The P8 ledger is implemented and bounded. Its initial limits are:

```text
64 refs per turn
16 retained selected excerpts
8 KiB per excerpt
64 KiB total ledger
```

The ledger supports deduplication, restore, stale/conflict representation and bounded
continuation/citation state. It is not an unlimited copy of logs, source, documents
or business data.

Durability is used only when continuation/reconnect requires it; raw search/fetch
payload growth must not become conversation storage.

## 6. Access and freshness

Search/fetch always operates under an effective context. A ref binds its access scope
and provider locator; fetch rechecks current access rather than trusting an old ref.

Freshness is explicit:

```text
current
stale
unknown
missing
revoked
```

Fingerprint mismatch should be surfaced as stale Evidence, not silently merged into
an old conclusion.

## 7. Routing policy

`EvidenceRoutingPolicy` prioritizes evidence classes without introducing a rigid
intent router.

Direction:

```text
business/current state      -> live ORM
installation behavior       -> runtime/schema/source/XML/config
standard HOW_TO              -> official/versioned docs + local verification
error diagnosis              -> turn trace + logs + source/XML/runtime
company policy               -> Knowledge/document sources
module/repository HOW_TO     -> manifest/README/docs/source/scripts + install state
current external fact        -> web when allowed
repository preflight         -> web/repo metadata + bounded static inspection
```

Conflicting evidence should be preserved/disclosed, not silently collapsed into a
single unsupported truth.

## 8. Live Odoo business truth

Frequently changing records such as sales orders, invoices, stock quantities and
contacts should normally be queried live under current ACLs/record rules.

Do not make mutable business truth primarily depend on a document/vector index.
Scale live analysis using bounded server-side primitives such as pagination,
aggregates and safe relation traversal rather than dumping large raw record sets into
the model.

## 9. Runtime/schema/configuration evidence

P8.2 currently implements installation inventory. Later P8 providers should add:

- effective models/fields and schema explanations;
- menus/actions/views and configuration;
- groups/ACL/record-rule/company explanations;
- capability/provider/configuration health.

These facts may also be exposed as compact ContextProvider data when directly
relevant.

## 10. Source/XML/module documentation

P8.4 should build installation-local source intelligence before reaching for a heavy
external graph stack by default.

Required evidence classes include:

```text
manifest / README / docs
model + field + method symbols
Python inheritance/overrides
XML IDs / views / inherit_id / xpath chains
menus/actions/buttons/wizards
requirements/dependencies
commands / scripts / flags / parameters
install/update/uninstall notes
troubleshooting/security notes
tests/examples where useful
```

Rules:

- preserve module/path/symbol/source provenance;
- use logical locators and approved current-source scopes;
- fingerprint content so stale refs are detectable;
- return bounded excerpts;
- source/document text remains untrusted data;
- distinguish normal-user operation from Odoo administration and host/technical operation.

Source modification is a separate later patch/test/deploy workflow.

## 11. Logs and diagnosis

Logs are Evidence, not prompt dumps.

A later provider should support bounded search by time/component/severity/terms plus
small surrounding context and correlation with turn/action/record/source state.

For ambiguous effects, diagnosis must not imply a failed model response means no
write occurred. Host verification/recovery state stays authoritative.

## 12. Company Knowledge / Sources

P9 should make Knowledge Odoo-native and editable by administrators/users with a clear
source lifecycle:

```text
uploaded/discovered -> processing -> indexed -> active
                                  \-> error
```

Support persistent sources and temporary conversation attachments. Keep the retrieval
backend independent from the LLM provider.

Start with deterministic extraction/structure and PostgreSQL lexical/FTS where
suitable. Add embeddings/vector/hybrid ranking when evals demonstrate a material
recall/answer-quality gain.

## 13. Web and repository Evidence

Web is a later Evidence source, especially useful for current external facts and
repository/module preflight.

Arbitrary repositories can be candidates. Preflight should combine repository
metadata/reputation signals with manifest/license/dependency analysis and bounded
relevant static inspection. Allowlists can be optional trust/policy signals, not a
global prerequisite.

Retrieved web/repository content is untrusted and cannot grant authority.

## 14. Citations

Final answers should be able to expose safe citations that resolve from Evidence
metadata without exposing raw host paths or inaccessible records.

Citation quality requires:

```text
source identity
logical locator
provenance
captured_at/fingerprint/freshness
access-safe display metadata
bounded excerpt where appropriate
```

Citation UX is not yet complete merely because P8 contracts contain citation metadata.

## 15. Security rules

- effective Odoo access remains authoritative;
- fetch revalidates current access;
- no secret/raw prompt/private reasoning in Evidence;
- document/source/log/web text never becomes system/tool policy;
- no arbitrary filesystem traversal or shell to compensate for incomplete indexing;
- no raw unlimited payload persistence;
- technical host details are restricted by product profile and Odoo permissions.

## 16. Current implementation/validation boundary

Implemented now:

```text
Evidence contracts/catalog/routing/ledger
CapabilityProvider Evidence composition
Skill Evidence selectors
manifest evidence_provider_ids seam
runtime/installation inventory EvidenceProvider
source-scope policy
focused tests prepared
```

Still pending:

```text
focused P8 test execution
live Evidence orchestration in ordinary turns
source/XML/module-doc providers
logs/self-diagnosis
company Knowledge/RAG
citation UX
web/repository Evidence
```

See `EVIDENCE_ARCHITECTURE.md`,
`research/P8_EVIDENCE_CORE_IMPLEMENTATION.md` and
`research/EXECUTION_STATE.md`.
