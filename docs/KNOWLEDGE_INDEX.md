# Knowledge, Evidence and Retrieval

This document supersedes the former sidecar PostgreSQL FTS Knowledge Index specification.

`CURRENT_STATE.md` remains authoritative for what exists now. This document defines the current target retrieval architecture used by the product roadmap.

## 1. Current state

The active embedded capability package currently contains:

```text
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

It does **not** currently contain a general document RAG provider, `knowledge.search`, `knowledge.read_excerpt`, source/XML structural search, log retrieval or vector search.

The retired Assistant Service's SQLAlchemy/Alembic knowledge/source implementation is historical evidence only. Useful concepts may be reimplemented inside Odoo; the sidecar database/API is not restored.

## 2. Product objective

Retrieval is broader than `vector RAG`.

The Assistant should be able to investigate the concrete installation using the most appropriate evidence source and iterate as needed:

```text
Evidence layer
  |
  +-- LIVE
  |     Odoo business data
  |     runtime/module/schema/configuration
  |     Odoo logs/tracebacks
  |     PostgreSQL/host diagnostics
  |
  +-- STRUCTURED / INDEXED
  |     Python/XML/source index
  |     company documents / attachments / Knowledge
  |     lexical PostgreSQL FTS
  |     semantic/vector index where evals justify it
  |
  +-- EXTERNAL
        web search/fetch
        future connectors
```

A question about the current installation may combine several providers before the final answer.

Example:

```text
"¿Por qué no aparece Margen en este presupuesto?"
  -> current record/screen
  -> installed module inventory
  -> model/schema
  -> active/inherited views
  -> relevant source/XML overrides
  -> user groups/permissions
  -> optional documentation
  -> answer with installation evidence
```

## 3. Agentic hybrid retrieval

Do not run one generic vector search before every provider turn.

Target behavior:

```text
small reliable BaseContext
  -> reasoning provider
      -> enough evidence? answer
      -> otherwise choose EvidenceProvider/search
      -> inspect returned refs/excerpts
      -> search another provider if useful
      -> synthesize
```

The host may require evidence even when the provider does not request it spontaneously for assertions that must be installation-specific, security-sensitive or verified before an effect.

Retrieval depth is controlled by exploration/cost/latency budgets, not by an arbitrary assumption that one search is enough.

## 4. Evidence contract

All retrieval mechanisms should normalize into one bounded host-owned contract rather than leaking storage-specific shapes into the agent loop.

Conceptually:

```text
Evidence
  evidence_id
  kind
  provider/source_id
  logical locator
  title
  bounded excerpt/data
  provenance
  fingerprint/version
  captured_at
  freshness/status
  trust classification
  access scope
  retrieval method/score where relevant
  citation metadata
```

Exact fields are fixed by the implementation phase/ADR/tests.

Evidence is **data**. It can support a conclusion; it cannot modify capability availability, system policy, technical profile or approval rules.

## 5. EvidenceLedger

The future agent runtime needs bounded references to evidence used during a task/conversation.

The ledger should support:

- provider continuation without re-dumping all source data;
- citations/provenance in final answers;
- conversation references to earlier evidence;
- freshness/fingerprint revalidation;
- diagnosis/evals of why an answer was grounded.

It must not become an unlimited copy of logs, source code, business data or documents. Retain logical refs, bounded excerpts/metadata and TTL/version rules appropriate to the source.

## 6. Evidence routing and authority

There is no universal `source A always beats source B` ranking.

Use intent-aware routing.

Examples:

### Concrete installation question

```text
current runtime/config/source/live Odoo facts
  > generic documentation
```

### Standard product navigation question

```text
official/current product documentation may be first
  -> verify installation if modules/version/customization could change the answer
```

### Business state question

```text
live ORM/aggregate result
  > indexed snapshot/document statement
```

The future `EvidencePolicy` may require verification from particular source classes for specific tasks.

## 7. Live Odoo business truth

Do not make frequently changing records such as `sale.order`, `account.move`, `stock.quant` or `res.partner` primarily depend on RAG indexing.

Use live schema-first capabilities for authoritative current values.

For larger investigations, extend live query contracts with safe server-side mechanisms such as:

```text
pagination/cursors
bounded relation traversal
aggregates/read_group
continuation refs
server-side summaries/analytics
```

Do not solve scale by dumping tens of thousands of raw records into one prompt.

## 8. Runtime/schema/configuration evidence

Installation-local facts should be retrievable through current Odoo authority:

- Odoo version/database/company context;
- installed modules and versions/dependencies;
- effective models/fields;
- view/action/menu relationships;
- selected safe configuration;
- capability/provider configuration health.

These facts may also act as ContextProviders where small enough and directly relevant.

## 9. Source/XML intelligence

Source intelligence is a first-class target and may be more valuable than embeddings for many Odoo technical questions.

Reintroduce useful old concepts as embedded providers/capabilities, for example:

```text
source.find_symbol
source.find_model_extensions
source.find_view_relations
source.find_xml_id
source.read_excerpt
```

Rules:

- use approved source roots;
- return logical refs rather than encouraging arbitrary path traversal;
- preserve module/path/symbol provenance;
- fingerprint source so stale refs are detectable;
- bound excerpts/bytes;
- source text is untrusted data, not model authority.

Source **modification** is a separate later Developer-only workflow.

## 10. Logs and diagnostics

Logs should be queried as structured evidence, not appended wholesale to prompts.

A log provider should support bounded search fields such as:

```text
time window
component/logger
severity
request/turn/user hints
model/record/action hints
semantic/keyword query
```

Then a bounded `read_context(ref)` retrieves surrounding lines/traceback frames.

A request like `analiza el último error que tuve al confirmar este pedido` should correlate likely record/action/time/traceback candidates. It should not assume the final log error is the user's error if evidence suggests otherwise.

PostgreSQL/host diagnostics follow the same pattern. Privileged access is controlled separately by the Developer/Operator host-operation phase.

## 11. KnowledgeSource product

Company/user-managed knowledge should be represented by Odoo-native source records.

Target lifecycle:

```text
uploaded/discovered -> processing -> indexed -> active
                                \-> error
```

A source should track at least:

```text
type/title
original artifact/reference
access scope
version/fingerprint
processing/index status
last successful processing
configuration/index metadata
```

Initial product scope should favor files manually uploaded to Odoo. External Drive/SharePoint/etc. connectors can be added later without changing the Evidence contract.

## 12. Ingestion pipeline

Target:

```text
artifact/source
 -> extract
 -> detect structure
 -> normalize
 -> segment coherently
 -> index
 -> validate
 -> active
```

Large documents are processed in bounded jobs/chunks. They are not passed wholesale to the model.

The Assistant may initiate this pipeline conversationally. Example:

> Añade este PDF al conocimiento de la empresa.

The chat action should create the KnowledgeSource, launch/monitor processing and report success/problems through normal capability/activity semantics.

## 13. Retrieval stages

### Stage 1 — structured + lexical

Start with deterministic structure and PostgreSQL/Odoo-native lexical/FTS retrieval where it performs well.

A useful logical API remains:

```text
knowledge.search(query, scope, limits)
  -> ranked logical refs + metadata

knowledge.read_excerpt(ref)
  -> bounded current excerpt + fingerprint
```

### Stage 2 — semantic/hybrid only with evidence

Before choosing pgvector, another vector DB, embedding model or reranker, create a representative retrieval/e2e eval set.

Add semantic/vector retrieval only if it materially improves recall/task success over lexical/structured retrieval for actual target corpora.

If added, semantic results must retain the exact same source ACL, provenance, fingerprint and citation behavior.

Apexive's current `llm_tool_knowledge` is a useful functional reference: semantic search, keyword+semantic hybrid retrieval, collection scoping and citations. It is not a reason to copy its storage/runtime architecture.

## 14. Files, images and multimodal evidence

Artifacts should be represented by bounded Odoo refs, not base64 in model prompts.

Depending on MIME/provider features:

```text
PDF -> text/layout extraction -> OCR fallback -> optional Knowledge ingestion
image -> provider vision or OCR -> Evidence
CSV/XLSX -> structured parser -> DataImport workflow / Evidence
```

`ProviderProfile` decides whether native vision/file input is available, host-emulated or unavailable.

## 15. Web evidence

Future web access is search/fetch evidence, not browser automation authority.

Use it when:

- the user explicitly asks for external/current information; or
- installation/company evidence is insufficient and policy permits external lookup.

Store URL/title/date/snippet/fetch provenance and treat content as untrusted.

## 16. ACL and prompt-injection boundary

Before evidence is returned to the reasoning provider:

- caller/source ACLs apply;
- secrets are excluded/redacted rather than indexed because they were technically readable;
- byte/record/chunk limits apply;
- retrieved instructions cannot modify policy or capability authority.

Required adversarial tests include documents/source/log lines that attempt to instruct the model to reveal secrets, call hidden tools or ignore host rules.

## 17. Freshness/invalidation

Evidence derived from mutable sources must have an explicit freshness/fingerprint strategy.

At minimum handle:

```text
source document replaced/deleted
authorization changed
source code changed
module updated
index version changed
record/live fact changed
```

Stale evidence is refreshed/rejected according to source class. Do not silently cite an old excerpt as current installation truth.

## 18. Testing and promotion

The roadmap requires deterministic, agentic and real gates before promoting each layer.

Evidence phase must test source/log diagnosis, provenance, stale refs, conflicts and injection boundaries.

Knowledge phase must test upload/ingest, large documents, lexical retrieval, citations, ACL, reindex and chat-driven ingestion.

If semantic/vector retrieval is added, promotion additionally requires measured retrieval/task-quality gain (`P9-REAL-SEMANTIC-GAIN`), not merely successful embedding generation.

See `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` and `research/REAL_ENV_VALIDATION_PROTOCOL.md`.
