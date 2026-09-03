# Knowledge, Evidence and Retrieval

This document supersedes the retired sidecar PostgreSQL FTS Knowledge Index design.
Current code/ADRs plus `CURRENT_STATE.md` and `research/EXECUTION_STATE.md` are
authoritative.

## 1. Current state

P8 is accepted and provides the shared embedded Evidence foundation plus live
installation/source/XML/log providers:

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
assistant.installed_source
assistant.odoo_log
```

P9's first coherent slice is accepted on main at
`77d470febf67ddee46562907718dc47e975922bb`:

```text
odoo.ai.knowledge.source
odoo.ai.knowledge.chunk
odoo.ai.knowledge.attachment
assistant.company_knowledge
assistant.knowledge.ingest_attachment
PostgreSQL lexical/FTS company-document retrieval
bounded temporary chat attachment transport
```

The retired Assistant Service SQLAlchemy/Alembic knowledge/source implementation is
historical evidence only. Its concepts may be reimplemented inside Odoo; its API,
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

Current/target pattern:

```text
small reliable BaseContext
 -> reasoning provider
     -> question-sensitive Evidence routing
     -> inspect bounded refs/items from effective providers
     -> fetch/search another source when useful
     -> synthesize with provenance
```

P8 ordinary turns already use this Evidence path for supported technical questions.
P9 extends the same routing seam to company-document language; it does not add a
parallel RAG agent or intent router.

The host may require installation-local evidence for claims that must be current,
installation-specific or safety-critical.

## 4. Evidence contract

Every retrieval mechanism normalizes to the host-owned Evidence contracts rather than
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

The bounded ledger limits remain:

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

Fingerprint mismatch or source-version change is surfaced as stale Evidence, not
silently merged into an old conclusion. P9 company Knowledge uses source version plus
chunk fingerprint for this revalidation.

## 7. Routing policy

Evidence routing prioritizes source classes without introducing a rigid intent router.

Direction:

```text
business/current state      -> live ORM
installation behavior       -> runtime/schema/source/XML/config
standard HOW_TO              -> official/versioned docs + local verification
error diagnosis              -> turn trace + logs + source/XML/runtime
company policy/manual        -> Knowledge/document sources
module/repository HOW_TO     -> manifest/README/docs/source/scripts + install state
current external fact        -> web when allowed
repository preflight         -> web/repo metadata + bounded static inspection
```

P9 adds company-document hints through a subclass of the shared routing policy. An
explicit evidence kind still wins. Generic/social turns still select no Evidence when
nothing relevant is requested.

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

P8 currently provides bounded installation/runtime inventory plus source/XML and
configured-log evidence. Runtime/schema/configuration expansion may still add richer:

- effective model/field explanations;
- menus/actions/views and configuration;
- groups/ACL/record-rule/company explanations;
- capability/provider/configuration health.

These facts may also be exposed as compact ContextProvider data when directly
relevant.

## 10. Source/XML/module documentation

P8 built installation-local source intelligence before reaching for a heavy external
graph stack.

Current design rules remain:

- preserve module/path/symbol/source provenance;
- use logical locators and approved current-source scopes;
- fingerprint content so stale refs are detectable;
- return bounded excerpts;
- source/document text remains untrusted data;
- distinguish normal-user operation from Odoo administration and host/technical operation.

Future semantic enrichment may add more explicit model/field/method/view inheritance
relations and validators, but should preserve local installation evidence as the
source of truth. Source modification is a separate later patch/test/deploy workflow.

Company Knowledge retrieval is proactive: substantive user questions first probe the
effective user's internal Knowledge even when the user does not say "RAG", "source" or
"reference". Odoo/configuration/module/error questions additionally route to bounded
runtime and installed source/XML Evidence so documented behavior can be compared with
the actual installation. Social-only turns remain retrieval-free, and internal/current-turn
sources are ordered ahead of any external provider.

Broad overview questions (for example, how an organization's network and systems are
set up) request panoramic document coverage. If the best matching Knowledge source is
short enough to fit the existing 64 KiB evidence budget and has at most eight chunks,
the provider returns all of its current chunks in document order. Narrow questions keep
the normal four ranked fetches. Longer documents retain ranked bounded retrieval rather
than silently flooding the model context. The answer-detail preference never removes
evidence needed for correctness.

## 11. Logs and diagnosis

P8 configured-log Evidence supports bounded correlated diagnosis. Logs remain
Evidence, not prompt dumps.

For ambiguous effects, diagnosis must not imply a failed model response means no
write occurred. Host verification/recovery state stays authoritative.

## 12. Company Knowledge / Sources

P9 first-slice implementation uses Odoo-native records and the lifecycle:

```text
uploaded -> processing -> indexed -> active
                      \-> error
```

Persistent sources carry owner, company, access mode, fingerprints, version and index
metadata. Temporary conversation uploads are separate expiring records and do not
become Knowledge merely because a file was attached.

Initial deterministic ingestion supports:

```text
PDF / TXT / Markdown / RST / CSV / JSON / XML
8 MiB max file/source
6,000 characters per chunk
2,048 chunks per source
```

Binary data stays in Odoo attachments. Odoo detects the media type from the uploaded
filename; the user never supplies or edits it. PDF text is extracted with the PDF reader
already provided by the Odoo Python environment. Image-only PDFs require OCR before upload.

The runtime sees a host-controlled attachment descriptor plus bounded extracted sections
through `assistant.turn_attachment` Evidence. Attachment text is untrusted current-turn data,
never instruction or authority. It can answer the user's immediate question without first
persisting the file as company Knowledge.

Derived chunks are host-owned. Normal users cannot create/update/delete index chunks
directly. Source reads/writes are constrained by effective Odoo owner/company record
rules. `company` sources are visible in active allowed companies; `private` sources
are owner-only.

Lexical retrieval uses parameterized PostgreSQL FTS with a GIN expression index and
an exact-substring fallback. `assistant.company_knowledge` normalizes results into
`DOCUMENT` Evidence with `USER_CONTENT` trust and source/version/chunk citations.

Fetch rechecks current ORM access, enabled/state/version and chunk fingerprint.
Changed/reindexed references become stale; disabled sources are revoked.

### Chat ingestion

The Assistant composer can upload a bounded temporary source and show a pending file
chip. The visible UX states that persistence requires an explicit user request.

On the next new turn the browser sends only an opaque attachment token marker. The
server validates ownership/expiry, strips the marker from the persisted visible user
message, retains safe filename/type/size metadata for the visible message and adds a
bounded host descriptor to the durable runtime input.

`assistant.knowledge.ingest_attachment` is a normal plan capability. It can act only
on an attachment already bound to the current turn, creates the source under the
effective user Environment, queues indexing and verifies the resulting source link.
It does not grant any authority from file content.

### Deferred intentionally

```text
OCR for image-only PDFs
XLSX-specific parsing
embeddings/vector store/semantic reranking
bulk source import
```

Embeddings should be added only if evals demonstrate a material recall/answer-quality
gain over the lexical baseline.

## 13. Web and repository Evidence

Web is a later Evidence source, especially useful for current external facts and
repository/module preflight.

Arbitrary repositories can be candidates. Preflight should combine repository
metadata/reputation signals with manifest/license/dependency analysis and bounded
relevant static inspection. Allowlists can be optional trust/policy signals, not a
global prerequisite.

Retrieved web/repository content is untrusted and cannot grant authority.

## 14. Citations

P8 final-answer results already carry safe host-owned citation metadata. P9 company
Knowledge contributes citations containing source UUID/name, source version, chunk
sequence and character range without exposing raw attachment bytes or inaccessible
records.

Citation quality requires:

```text
source identity
logical locator
provenance
captured_at/fingerprint/freshness
access-safe display metadata
bounded excerpt where appropriate
```

Rich browser navigation for company Knowledge citations is still future UX work; the
metadata contract exists now.

## 15. Security rules

- effective Odoo access remains authoritative;
- fetch revalidates current access;
- no secret/raw prompt/private reasoning in Evidence;
- document/source/log/web text never becomes system/tool policy;
- no arbitrary filesystem traversal or shell to compensate for incomplete indexing;
- no raw unlimited payload persistence;
- temporary upload tokens are user-bound, expiring and opaque;
- visible user messages never persist the internal attachment marker;
- source ownership/company/lifecycle metadata cannot be forged by normal RPC writes;
- derived chunk mutation is host-owned;
- the fixed FTS SQL is parameterized host code, not an exposed SQL capability;
- technical host details are restricted by product profile and Odoo permissions.

## 16. Current implementation/validation boundary

Implemented and P8-accepted:

```text
Evidence contracts/catalog/routing/ledger
CapabilityProvider Evidence composition
Skill Evidence selectors
manifest evidence_provider_ids seam
runtime/installation inventory EvidenceProvider
installed source/XML EvidenceProvider
configured-log EvidenceProvider
ordinary-turn Evidence orchestration
safe final citation metadata
source-scope/access/freshness policy
```

Implemented and accepted in P9 first slice:

```text
company Knowledge source/chunk lifecycle
bounded deterministic ingestion
PostgreSQL lexical/FTS + GIN index
company Knowledge EvidenceProvider
company-document routing
ACL/freshness/citation behavior
temporary chat upload + durable turn binding
chat-driven Knowledge ingestion capability
Assistant attachment UI
focused and seven real gates PASS
```

Still pending beyond this slice:

```text
PDF/OCR and richer file parsing
semantic/vector retrieval if justified by evals
rich Knowledge citation navigation
web/repository Evidence
```

See `EVIDENCE_ARCHITECTURE.md`, `research/P9_KNOWLEDGE_FIRST_SLICE.md`,
`research/P9_FOCUSED_VALIDATION_RUNBOOK.md`,
`research/evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md` and
`research/EXECUTION_STATE.md`.
