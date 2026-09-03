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

## 2. Reused product seams

The slice reuses rather than replaces current architecture:

- the existing short-lived current-turn attachment contract as the artifact entry
  point;
- `agent_model_is_eligible()` and effective-user model ACL checks;
- `visible_action_preview_fields()` as the field-authority ceiling;
- the existing capability registry, PLAN preview/policy/verification lifecycle and
  EffectJournal metadata;
- Odoo's native `base_import.import` parser/importer for CSV parsing, mapping
  suggestions, dry-run validation and `skip`/`limit` batch semantics;
- native `ir.cron` instead of introducing OCA `queue_job` as a dependency.

The Odoo 18 importer is especially useful because `parse_preview()` already performs
header/type inspection and mapping suggestions, while `execute_import(...,
dryrun=True)` validates through the same import path and rolls back the test write.
Its `skip`, `limit` and `nextrow` semantics are reused for chunk progression.

OCA `base_import_async`/`queue_job` remain useful operational references for breaking
large imports into background units, but this slice keeps the existing embedded
Odoo-native scheduler because it is sufficient for the current contract.

## 3. Durable artifact/session contract

New models:

```text
odoo.ai.data.import.session
odoo.ai.data.import.chunk
```

The short-lived attachment is copied into the durable session before the background
worker starts. The session stores bounded metadata and fingerprints rather than
placing file contents in the model prompt:

```text
session_uuid
owner / company / originating turn/conversation
source attachment ref
filename / mimetype / size / SHA-256
copied Binary artifact
target model
headers
explicit mapping
native import options
request + mapping fingerprints
chunk size / row counters / state
```

A source attachment expiring after the turn therefore does not invalidate an already
queued import.

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
the exact artifact, model, mapping, exact mapped row count, duplicate-row count and
chunk size. Execution persists an idempotent session and queues background work.
The capability is marked `recovery_mode=segmented` and
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

Session/chunk lifecycle fields are host-owned. Internal users receive read access to
their own company-scoped records; direct user create/write/unlink is denied by model
methods/ACLs. Cron reconstructs an Odoo Environment for the recorded owner with
`su=False` before touching the target business model.

## 6. Chunk execution and no-blind-replay rule

The worker claims at most one queued session chunk using a fixed
`FOR UPDATE SKIP LOCKED` query over the Assistant's own session table. The row lock,
native import and durable chunk receipt live in the same PostgreSQL transaction.

For every chunk:

```text
revalidate user/company/model/fields/artifact
 -> determine bounded input window
 -> Odoo native dry-run
 -> real Odoo native import
 -> persist record ids + receipt fingerprint
 -> advance next_row/counters
 -> commit
```

This gives the required replay invariant:

- crash/failure before transaction commit => imported rows and receipt/offset roll
  back together, so retrying that chunk is safe;
- successful commit => receipt and next offset commit with the rows, so a later cron
  does not blindly execute the completed chunk again.

The default chunk size is 250 rows and the host ceiling is 1,000 rows per chunk.
Only one chunk is handled per cron transaction; if more work remains the cron is
triggered again.

## 7. Partial-invalid semantics

The worker dry-runs each chunk before its real import. If Odoo reports validation
messages, **the whole current chunk is rejected** and no row in that chunk is written.
Previously committed chunks remain valid and are never replayed.

The session becomes:

```text
failed   if no earlier chunk committed
partial  if earlier chunks committed
```

The rejected chunk records exact input/failed counts, a bounded sanitized message set
and a receipt fingerprint. Rows after the rejected chunk remain unprocessed and are
reported as `remaining_rows`.

This is the declared first-slice partial-invalid behavior; row-by-row salvage inside
a failed chunk is deliberately deferred rather than silently weakening transaction
semantics.

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
