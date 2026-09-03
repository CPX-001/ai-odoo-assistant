# Current implementation state

This is the current-state entry point for the supported Odoo 18 product on `main`.
For the exact roadmap cursor and validation truth use
[`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Accepted lineage

```text
P0-P10 COMPLETE / ACCEPTED
P10 accepted at bde508b737c132140e237cdfde31aee9b37eca5f
P11 ADVANCED IMPORTS CORE IMPLEMENTED / VALIDATION PENDING
```

P10 remains the latest accepted phase. P11 code and prepared tests are not PASS
evidence.

Current P11 records:

```text
research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
research/P11_IMPORT_CLEANUP_REPAIR_SLICE.md
research/P11_FOCUSED_VALIDATION_RUNBOOK.md
```

## 1. Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported addon: `addons/odoo_ai_assistant`.
- Current addon version: `18.0.13.31.0`.
- Dependencies: `account`, `base`, `base_import`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Odoo/PostgreSQL own conversations, turns, effects, recovery, Evidence, Knowledge and
  durable import state.
- Long turns, Knowledge ingestion and large import chunks use native `ir.cron` work.
- Business operations execute as the effective Odoo user with `su=False`.
- Codex App Server remains the current ephemeral reasoning-provider subprocess.
- The retired Assistant HTTP sidecar is not a supported runtime.

The optional P10 AF_UNIX broker is only a finite machine-privilege adapter for typed
Technical host operations. It runs no model and owns no Assistant turn/import state.

## 2. Authority model

The model proposes. Odoo/host code owns:

```text
user/company/group identity
ACLs / record rules / field access
capability identity/schema/availability
policy / autonomy / approval
EffectPlan and write barrier
execution / verification / recovery / receipts
Evidence/Knowledge access and provenance
artifact/model/mapping validation
import staging / cleanup rules / cursor / repair revision / chunk receipts
```

`CapabilityDefinition` remains the atomic executable contract. No arbitrary SQL,
Python, shell, sudo or unrestricted ORM-method surface is exposed to the model.

Protected effects keep:

```text
discover -> prepare/preview -> policy -> approval when required
 -> durable barrier -> execute -> verify -> receipt/recovery
```

Approval can never enlarge Odoo or broker authority.

## 3. Durable agent runtime

The accepted runtime provides durable conversations/turns, leases and stale recovery,
per-conversation causality with cross-conversation concurrency, provider-neutral
`NextDecision`, TaskPlan vs EffectPlan, bounded multi-step effects, EffectJournal,
interventions/cancellation, public activity/answer streaming, immutable turn settings,
resource references and post-effect reasoning.

Public answers use paced real deltas, streaming-safe Markdown and final reconciliation.
Immutable turn settings include adaptive Concise/Normal/Extensive response detail,
with Normal as the initial administrator default and no fixed length quota.

P7-P11 extend that runtime rather than creating a second scheduler, agent service or
database.

## 4. Extensions, Evidence and Knowledge

The current extension framework includes `CapabilityProvider`, Skills,
ContextProviders, EvidenceProviders, provider feature negotiation, effective manifests,
installed-addon provider discovery and progressive disclosure. Executable authority
still resolves through the same capability registry/executor/policy path.

P8 supplies bounded provenance/freshness/access-aware installation Evidence including
runtime, installed-addon source/XML and configured logs. P9 supplies Odoo-native
company Knowledge with deterministic bounded document ingestion, PostgreSQL lexical
FTS, citations, stale-version revalidation and ordered whole-source coverage for a
best-matching short document when a broad overview is requested. Retrieved/file text
is data, never policy.

Product-facing profiles remain exactly `user` and `technical`; autonomy is independent
from technical reach.

## 5. Technical host operations — accepted P10

Accepted Technical capabilities include:

```text
odoo.module.inspect
postgres.health
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

ADR-024 governs the optional broker: exact logical targets, `SO_PEERCRED`, bounded
request/receipts, fixed argv, durable replay ledger, explicit uncertainty and the
external lifecycle-safe module-update adapter. Generic shell, module install/uninstall,
repository/package promotion and secret reveal are not implied.

## 6. Advanced imports/artifacts — P11 implemented core

P11 now implements a durable create-only CSV workflow rather than decomposing a large
file into hundreds or thousands of ordinary CRUD tool calls.

Durable models:

```text
odoo.ai.data.import.session
odoo.ai.data.import.chunk
```

Capabilities:

```text
assistant.data_import.inspect_csv       READ
assistant.data_import.start_csv         PLAN / ACTION / POLICY
assistant.data_import.status            READ
assistant.data_import.inspect_cleanup   READ
assistant.data_import.start_clean_csv   PLAN / ACTION / POLICY
assistant.data_import.inspect_rejected  READ
assistant.data_import.resume_csv        PLAN / ACTION / POLICY
```

### Import preparation

The flow begins with a bounded current-turn CSV attachment. Odoo 18 `base_import`
provides parsing/type/mapping suggestions. The host then limits the target to an
eligible model the effective user may create and limits mapping to direct writable
scalar fields:

```text
boolean / char / date / datetime / float / integer / monetary / selection / text
```

The selected mapped rows are normalized/staged once, bounded by staged-payload and
chunk-count ceilings, fingerprinted and copied into the durable session together with
the original artifact provenance. Binary/base64 or the complete staged table is not
dumped into the model prompt.

### Chunk execution and recovery

Default chunk size is 250 rows; maximum is 1,000. Each cron invocation claims at most
one queued session with fixed `FOR UPDATE SKIP LOCKED` SQL over the Assistant's own
table and imports only the next staged chunk under the originating effective user with
`su=False`.

Business rows, cursor advance and a successful chunk receipt share the same PostgreSQL
transaction. A pre-commit crash rolls them back together; a committed chunk is not
blindly replayed.

Odoo validation errors reject the whole current chunk. The chunk write rolls back,
then a bounded rejected receipt is recorded. Earlier completed chunks remain intact.

### Deterministic cleanup/enrichment

The model may propose only these finite host-owned cleanup operations over fields
already present in the approved mapping:

```text
trim
normalize_whitespace
replace_exact
set_if_empty
```

Cleanup preview reports exact changed-row counts, duplicate counts before/after,
bounded before/after examples and fingerprints. There is no expression evaluator,
script body or authority to introduce new fields.

`planned_corrected_rows` tracks changed staged rows. `corrected_rows` increases only
when those changed rows actually commit.

### Rejected-window repair/resume

After a rejection, the owner may inspect a bounded view of only that latest rejected
mapped-row window plus sanitized Odoo validation messages. A repair is explicit:

```text
row + already-mapped field + replacement value
```

The host revalidates user/company/model/fields, fingerprints the before/after staged
state, increments `repair_revision`, retains the historical rejected receipt and
requeues from the unchanged committed `next_row` cursor. The retry receives a new
receipt sequence; previously successful chunks are not replayed.

If the repair succeeds, unresolved aggregate `failed_rows` can return to zero while the
old rejected receipt remains visible as historical provenance.

### Explicit P11 breadth limits

Not claimed by the current core:

```text
XLS/XLSX/ODS durable sessions
relational import paths
external-id update/upsert
arbitrary transformation scripts/expressions
generic semantic matching against existing business records
automatic new chat turn/message on background completion
```

These are deferred breadth decisions, not missing authority shortcuts.

## 7. Validation truth

P10 remains accepted on immutable evidence.

P11 is currently:

```text
static/compile/lint                                      NOT EXECUTED
addon install/update + security/XML/model load           NOT EXECUTED
TestPhase11DataImportSession                             NOT EXECUTED — 4 prepared methods
TestPhase11DataImportCleanupRepair                       NOT EXECUTED — 4 prepared methods
P11-REAL-CSV-IMPORT                                      NOT EXECUTED
P11-REAL-LARGE-IMPORT                                    NOT EXECUTED
P11-REAL-MAPPING-CORRECTION                              NOT EXECUTED
P11-REAL-PARTIAL-INVALID                                 NOT EXECUTED
P11-REAL-RESUME-NO-DUPLICATE                             NOT EXECUTED
P11-REAL-IMPORT-RECEIPT                                  NOT EXECUTED
P11 acceptance                                           NOT COMPLETE
```

The immediate next action is to execute
[`research/P11_FOCUSED_VALIDATION_RUNBOOK.md`](research/P11_FOCUSED_VALIDATION_RUNBOOK.md),
repair failures if any, then run all six real P11 gates. Broad unrelated regressions
remain periodic debt unless a focused failure demonstrates wider blast radius.
