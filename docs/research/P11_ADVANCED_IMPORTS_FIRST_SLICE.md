# P11 advanced imports — first durable CSV slice

Date: 2026-09-03  
Status: **IMPLEMENTED / FOCUSED + REAL VALIDATION PENDING**

This record describes the first coherent Phase-11 implementation on top of accepted
P10. It is an implementation record, not PASS evidence.

## 1. Problem

The existing `odoo.records.batch_create` path is intentionally bounded to small
record sets. It is not an appropriate execution primitive for a CSV containing
hundreds or thousands of rows because repeating many ordinary CRUD calls would make
progress, recovery and duplicate prevention weak.

P11 therefore introduces a durable workflow whose authority remains Odoo-owned while
the model only proposes the target and explicit column mapping.

## 2. Reused product seams and external reference

The slice reuses rather than replaces current architecture:

- the existing short-lived current-turn attachment contract as the artifact entry
  point;
- `agent_model_is_eligible()` and effective-user model ACL checks;
- `visible_action_preview_fields()` as the field-authority ceiling;
- the existing capability registry, PLAN preview/policy/verification lifecycle and
  EffectJournal metadata;
- Odoo 18 `base_import.import` for CSV parsing, type inference, mapping suggestions and
  the final native chunk import;
- native `ir.cron` instead of introducing OCA `queue_job` as a product dependency.

Odoo 18 `parse_preview()` already performs header/type inspection, mapping suggestions
and bounded examples. `_convert_import_data()` normalizes the selected columns/rows,
while `execute_import()` ultimately uses the normal model `load()` path and its
savepoint/error semantics.

OCA 18 `base_import_async` was used as a concrete operational reference. It parses the
source file once, persists a normalized artifact, splits work into bounded chunks and
loads each chunk independently. The P11 slice follows that lesson without importing
OCA's scheduler stack: mapped rows are staged once inside the durable session and each
Assistant cron transaction receives only its bounded chunk.

## 3. Durable artifact/session contract

New models:

```text
odoo.ai.data.import.session
odoo.ai.data.import.chunk
```

The short-lived attachment is copied into the durable session before the background
worker starts. The session also persists the host-normalized mapped rows and their
fingerprint, so the worker does not repeatedly parse the full original CSV.

Durable state includes:

```text
session_uuid
owner / company / originating turn/conversation
source attachment ref
filename / mimetype / size / SHA-256
copied Binary artifact (system-only field access)
target model
headers
explicit mapping
normalized import field list
staged mapped rows (system-only field access)
staged-row fingerprint
safe native import options
request + mapping fingerprints
chunk size + planned chunk count
row counters / state
```

The staged mapped payload is bounded to 16 MiB and at most 4,096 planned chunks.
A source attachment expiring after the turn therefore does not invalidate already
queued work.

## 4. Capability surface

The automatically discovered provider exposes:

```text
assistant.data_import.inspect_csv   READ
assistant.data_import.start_csv     PLAN / ACTION / policy approval
assistant.data_import.status        READ
```

`inspect_csv` accepts only a current-turn attachment id plus a target model. It
returns bounded column examples, effective-user writable scalar fields and filtered
Odoo-native mapping suggestions.

`start_csv` requires an explicit `column_index -> field` mapping. Preview revalidates
the exact artifact, model, mapping, exact mapped row count, duplicate-row count, chunk
size and planned chunk count. Execution persists an idempotent durable session and
queues background work. The capability is marked `recovery_mode=segmented` and
`journal_classification=irreversible`; its immediate verified effect is the durable
queue request. Per-chunk business receipts live on the import session.

`status` returns exact imported/rejected/remaining counts plus bounded recent chunk
receipts.

## 5. Authority boundary

The first slice is deliberately create-only and narrower than Odoo's general import
UI.

A target must:

1. pass `agent_model_is_eligible()`;
2. remain readable and creatable by the originating effective user;
3. still pass those checks when a background chunk executes.

Mapped fields must come from `visible_action_preview_fields()` and, in this first
slice, are restricted to direct scalar types:

```text
boolean
char
date
datetime
float
integer
monetary
selection
text
```

Relational paths, external/database ids, binary/image import, arbitrary related-record
creation and protected/sensitive fields are not accepted in this slice.

Session/chunk lifecycle fields are host-owned. Internal users can read only their
company/owner-scoped session metadata through record rules; durable raw/staged content
fields are additionally restricted to the system group. Direct user lifecycle writes
are denied. Cron reconstructs an Odoo Environment for the recorded owner with
`su=False` before touching the target business model.

## 6. Chunk execution and no-blind-replay rule

The worker claims at most one queued session using a fixed
`FOR UPDATE SKIP LOCKED` query over the Assistant's own session table. The model cannot
supply SQL or alter that query.

The source CSV is normalized once during preparation. For every background chunk the
worker then performs:

```text
revalidate user / company / target model / current allowed fields
 -> verify persisted map/import-field binding
 -> slice only next staged mapped rows
 -> serialize bounded canonical UTF-8 CSV for that chunk
 -> Odoo native execute_import/load under effective user
 -> if native errors: rollback current chunk and persist rejected receipt
 -> if success: persist created record ids + receipt fingerprint
 -> advance next_row/counters
 -> commit
```

The default chunk size is 250 rows and the host ceiling is 1,000 rows. A session may
plan at most 4,096 chunks. Only one chunk is handled per cron transaction; if more work
remains the cron is triggered again.

The critical replay invariant is transactional:

- failure/process loss before transaction commit leaves business rows, receipt and
  cursor uncommitted, so the same durable offset can safely be attempted again;
- successful commit stores business rows, the receipt and the new offset together, so
  a later worker starts after that chunk rather than blindly replaying it.

## 7. Partial-invalid semantics

Each canonical chunk goes through Odoo's native import/load validation under the same
transaction. If Odoo returns an error, the current chunk's nested savepoint/transaction
path leaves zero rows from that chunk and the Assistant persists a bounded rejected
receipt after rollback. A successful prior chunk remains committed and is never
replayed.

The session becomes:

```text
failed   if no earlier chunk committed
partial  if earlier chunks committed
```

The rejected chunk records exact input/failed counts, a bounded sanitized message set
and a receipt fingerprint. Rows after the rejected chunk remain unprocessed and are
reported as `remaining_rows`.

This is the declared first-slice behavior. Row-by-row salvage inside a rejected chunk
is deliberately deferred rather than silently weakening transaction semantics.

## 8. Duplicate and mapping evidence

The prepare/preview path counts exact duplicate mapped rows inside the CSV and exposes
that number before authorization. Odoo-native suggestions are only suggestions: the
final model-proposed map must use current host-allowed fields and is fingerprinted.

Database-level semantic deduplication, model-assisted row cleanup/enrichment and
upsert/update matching are not part of this slice.

## 9. Explicit first-slice limits

Not yet implemented/promoted:

```text
XLS/XLSX/ODS import sessions
relational field import paths
external-id upsert/update
row-by-row salvage inside a rejected chunk
model-assisted row cleanup/enrichment with corrected-row receipts
user-driven remap/resume after a validation rejection
automatic final chat message when a background session completes
cross-session business duplicate matching
```

`corrected_rows` is present in the durable receipt/status contract but remains zero
until a later cleanup/enrichment slice defines a safe correction contract.

## 10. Validation truth

The implementation includes focused Odoo tests for:

- two-chunk CSV execution and idempotent session start;
- no replay after completion;
- partial invalid second chunk with the first receipt preserved;
- blocked-field mapping denial and user ownership boundary;
- segmented PLAN capability metadata.

Those tests are **prepared, not PASS**, until executed in the supported Odoo 18
environment. No P11 real gate is PASS from this implementation record alone.

Use `P11_FOCUSED_VALIDATION_RUNBOOK.md` next.
