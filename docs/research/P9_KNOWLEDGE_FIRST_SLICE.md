# P9 Knowledge first coherent slice

Updated: 2026-09-02
Status: IMPLEMENTED / FOCUSED VALIDATION NOT YET EXECUTED

## Scope

This slice implements the first Odoo-native company Knowledge path on top of the
accepted P8 Evidence architecture. It deliberately does not introduce a second RAG
runtime, vector database or generic parser service.

Implemented together because these parts form one usable product loop:

```text
admin/browser upload or temporary chat upload
  -> bounded Odoo Binary source
  -> uploaded / processing / indexed / active | error
  -> deterministic text extraction + chunks
  -> PostgreSQL lexical/FTS retrieval
  -> assistant.company_knowledge EvidenceProvider
  -> existing Evidence routing / ledger / citations

chat temporary attachment
  -> host-only attachment descriptor on durable turn
  -> assistant.knowledge.ingest_attachment capability
  -> persistent Knowledge source + background indexing
```

## Odoo-native source lifecycle

New models:

```text
odoo.ai.knowledge.source
odoo.ai.knowledge.chunk
odoo.ai.knowledge.attachment
```

A persistent source owns its Odoo user/company scope, access mode, content
fingerprint, indexed fingerprint, version, state and chunk count. Initial states are:

```text
uploaded -> processing -> indexed -> active
                      \-> error
```

An enabled successfully indexed source becomes `active`; a disabled indexed source
stays `indexed`. Reindexing increments the source version and replaces the derived
chunk set.

Temporary chat attachments are separate records with opaque tokens and a 24-hour
expiry. Uploading one does **not** automatically add it to Knowledge.

## Bounded ingestion

The initial deterministic parser accepts:

```text
TXT / Markdown / RST / CSV / JSON / XML
```

Initial hard bounds:

```text
8 MiB source/upload
6,000 characters per chunk
2,048 chunks per source
8 temporary attachments per turn
2 pending sources processed per cron pass
```

Binary content remains in Odoo attachments. The model receives only bounded host
metadata until an Evidence fetch returns a bounded excerpt. Raw base64 is never put
into the model prompt.

PDF/OCR and spreadsheet-specific parsing are intentionally deferred until a bounded,
deterministic parser is selected and validated. Embeddings/vector ranking are also
deferred until lexical retrieval evals show a measurable gap.

## Retrieval and Evidence

`assistant.company_knowledge` is a normal P8 `EvidenceProvider` with kind
`DOCUMENT`. Search uses authorized active source IDs from the effective user
Environment before executing parameterized PostgreSQL lexical/FTS search. A GIN
expression index backs the `simple` text-search configuration.

Each Evidence reference carries:

```text
source UUID/name
source version
chunk sequence + character range
chunk fingerprint
current user/company access scope
USER_CONTENT trust
safe citation metadata
```

Fetch rechecks current ORM access, source state/version and chunk fingerprint. A
changed/reindexed source returns stale Evidence rather than silently treating an old
reference as current. Disabled sources are revoked.

Company document text remains untrusted data. The provider cannot change tool policy,
capability availability, approvals or authority.

P9 extends the question-sensitive routing policy rather than adding an intent router.
Company-document language such as policy/manual/internal-company questions makes
`DOCUMENT` Evidence a preferred source; generic/social turns still do not force
retrieval.

## Chat ingestion

The Assistant composer can upload a bounded temporary file and shows it as a local
pending attachment. The UI tells the user that the file is only persisted to
Knowledge when they explicitly ask for that action.

The browser sends an opaque marker with the next new turn. The Odoo server:

1. validates that every token belongs to the effective user and is unexpired;
2. strips the marker before persisting the visible user message;
3. binds the upload to the durable turn;
4. appends only a host-controlled attachment descriptor to the runtime input;
5. preserves `client_request_id` idempotency and rejects cross-turn rebinding.

`assistant.knowledge.ingest_attachment` is the only executable boundary introduced by
this slice. It can ingest only an attachment already bound to the current turn. It
uses preview + verification and creates the persistent source under the effective
user Environment. The narrow host-owned link from the temporary upload to the source
is written only after that access check.

## Security boundaries

- Source creation under a non-superuser Environment forces owner and company to the
  effective user/current company; browser-supplied lifecycle/ownership fields are
  ignored or rejected.
- Source mutation is owner/company-scoped by Odoo record rules.
- Company sources are readable only in active allowed companies; private sources are
  owner-only.
- Derived chunk creation/update/deletion is host-owned. Normal users receive read-only
  chunk ACLs and cannot poison the index directly.
- Temporary attachments are immutable owner/company-scoped records; only narrowly
  validated host code binds them to turns/sources.
- The ingestion cron may use superuser authority only for derived index maintenance
  after the source has already been admitted into the Odoo-owned source model. This
  authority is not exposed as a capability or model tool.
- No arbitrary SQL is exposed. The only SQL added is fixed, parameterized host-owned
  FTS plus deterministic index creation.

## UI/admin surface

System administrators receive an `AI Knowledge` menu with source list/form views,
state, access mode, fingerprints, version/chunk metadata and explicit queue/process/
activate/disable actions.

The Assistant composer receives the bounded attachment control. This is a single
transport into the existing turn/capability runtime rather than a second chat flow.

## Focused validation prepared

Added deterministic coverage for:

```text
tests/unit/test_phase9_knowledge_routing.py
addons/odoo_ai_assistant/tests/test_phase9_knowledge.py
```

The Odoo test module covers source lifecycle, FTS retrieval, Evidence citations,
stale reindex refs, company/private ACLs, host-owned chunks, clean turn binding,
request-id retry safety and capability discovery.

## Validation status

No test or real-environment gate has been executed as part of the GitHub-connector
implementation session that produced this record. Therefore none is claimed PASS.

The next blocking step is focused validation and repair. After that, the P9 real
acceptance gates remain:

```text
P9-REAL-UPLOAD-INGEST
P9-REAL-CHAT-INGEST
P9-REAL-FTS
P9-REAL-CITATIONS
P9-REAL-ACL
P9-REAL-REINDEX
P9-REAL-LARGE-DOCUMENT
```

`P9-REAL-SEMANTIC-GAIN` remains conditional and should only exist if an embeddings
backend is introduced because eval evidence demonstrates a material gain.

## Deferred intentionally

```text
PDF/OCR parser
XLSX-specific parser
embeddings / vector store / semantic reranker
conversation attachment Q&A without persistence as a dedicated retrieval source
bulk source import
rich browser citation navigation for Knowledge
```

These are not required to validate the first lexical Odoo-native Knowledge loop.
