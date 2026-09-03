# P11 focused validation runbook

State: `EXECUTED / PASS / P11 ACCEPTED`
Scope: durable create-only CSV import core, including deterministic cleanup and rejected-window repair/resume

Acceptance evidence:
`evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`.

Implementation records:

```text
P11_ADVANCED_IMPORTS_FIRST_SLICE.md
P11_IMPORT_CLEANUP_REPAIR_SLICE.md
```

This runbook is incremental. It does not authorize the full addon/repository/browser
regression unless a focused failure demonstrates a wider blast radius.

## 1. Focused static/module gate

On the exact current `main`, compile/lint at minimum:

```text
addons/odoo_ai_assistant/models/data_import.py
addons/odoo_ai_assistant/models/data_import_repair.py
addons/odoo_ai_assistant/runtime/capabilities/providers/assistant_data_import.py
addons/odoo_ai_assistant/runtime/capabilities/providers/assistant_data_import_repair.py
addons/odoo_ai_assistant/tests/test_phase11_data_import.py
addons/odoo_ai_assistant/tests/test_phase11_data_import_repair.py
addons/odoo_ai_assistant/models/__init__.py
addons/odoo_ai_assistant/tests/__init__.py
addons/odoo_ai_assistant/__manifest__.py
```

Update the addon on a disposable Odoo 18 database so model extensions and these data
files are actually loaded:

```text
security/data_import_security.xml
security/ir.model.access.csv
data/data_import_cron.xml
```

Text syntax alone is not a substitute for the module update gate.

## 2. Focused Odoo gate

Run exactly the two P11 classes:

```text
/odoo_ai_assistant:TestPhase11DataImportSession
/odoo_ai_assistant:TestPhase11DataImportCleanupRepair
```

Expected coverage: **8 methods total** (4 + 4).

Required properties:

- current-turn CSV inspection returns bounded columns/examples and only effective-user
  safe scalar import fields;
- selected/mapped rows are staged once instead of reparsing the full source per chunk;
- start is idempotent for the same turn/artifact/model/mapping/chunk-size request;
- completed chunk receipts/cursors prevent replay;
- native validation rejection rolls back the whole current chunk while earlier
  committed chunks remain intact;
- blocked/unmapped fields cannot enter mapping, cleanup or repair;
- cleanup supports only the finite host-owned rule set and exposes exact bounded
  before/after evidence;
- `corrected_rows` remains zero while cleanup is merely queued and increases only when
  changed rows actually commit;
- the latest rejected mapped-row window can be inspected by the owner only;
- an explicit correction can requeue that rejected window without changing `next_row`;
- a successful repaired retry keeps the historical rejected receipt, adds a new
  completed receipt, clears the aggregate unresolved failure count and does not replay
  the earlier successful chunk;
- repair revision/fingerprint and planned chunk count advance coherently;
- cleanup/resume are PLAN + policy-controlled segmented irreversible effects; inspect
  capabilities remain READ_ONLY;
- all target business writes execute under the recorded effective user with `su=False`.

If a failure touches shared plan/recovery behavior, add only the necessary direct
neighbors such as `TestCanonicalPlanHostLoop` or `TestEffectJournal`. Do not widen
validation automatically.

## 3. Real product-path fixtures

Use browser/chat -> durable turn -> embedded runtime with:

- one normal internal user with create access on the disposable target model;
- a second user for ACL denial;
- CSV attachments below the existing 8 MB attachment ceiling;
- a small valid fixture;
- an ambiguous-header fixture;
- a fixture that benefits from deterministic cleanup;
- a partial-invalid fixture that can be repaired explicitly;
- a realistically large fixture several chunks long;
- a low chunk size where interruption/replay behavior must be observed.

Record exact SHA, Odoo/PostgreSQL version, user/profile/autonomy, session UUID, chunk
size/planned/actual counts, correction/repair revision, sanitized receipts and timing.
Do not persist raw customer files, staged row payloads or provider-private reasoning as
evidence.

## 4. P11-REAL-CSV-IMPORT

Attach a small CSV and ask the Assistant to inspect/import it.

Pass when the host preview binds exact artifact/model/mapping/row count/duplicate
count/chunk plan, policy is applied, exact intended records are created once, protected
columns are ignored/denied and final status counters match the database.

## 5. P11-REAL-LARGE-IMPORT

Use a realistically large disposable CSV.

Pass when preparation stages mapped rows once within the documented ceilings, each
worker invocation consumes only one bounded staged chunk, unrelated Odoo navigation
and another Assistant conversation remain usable, final imported count matches actual
records and no hundreds/thousands of tiny CRUD calls are required.

Record preparation, representative per-chunk and total duration.

## 6. P11-REAL-MAPPING-CORRECTION

Use an ambiguous header and at least one mapped value that merits deterministic
cleanup.

Pass when:

- Odoo-native suggestions/examples support a sensible mapping or clarification;
- the model can replace an incorrect suggestion but the host accepts only safe mapped
  fields;
- hostile header/value text cannot widen authority;
- if cleanup is proposed, only `trim`, `normalize_whitespace`, `replace_exact` or
  `set_if_empty` are accepted;
- cleanup preview shows exact changed-row and duplicate counts plus bounded samples;
- successful cleaned rows are reflected in non-zero `corrected_rows` only after commit.

No arbitrary expression/script or relational-field transformation is permitted.

## 7. P11-REAL-PARTIAL-INVALID

Use at least two chunks where an earlier chunk is valid and a later chunk is rejected
by Odoo native validation.

Pass when the earlier chunk/receipt commits, the invalid chunk writes zero business
rows, a bounded rejected receipt is stored after rollback, the session becomes
`partial`, and imported/failed/remaining counters are truthful.

Then inspect the rejected window through `assistant.data_import.inspect_rejected` and
confirm only already-mapped field values and sanitized messages are exposed.

## 8. P11-REAL-RESUME-NO-DUPLICATE

This gate has two required recovery cases.

**A. Process interruption:** interrupt/restart after at least one committed chunk. The
session must continue from the committed cursor and must not duplicate completed work.
A pre-commit interruption must leave neither business rows nor a false completed
receipt.

**B. Explicit rejected-window repair:** after a later chunk is rejected, propose an
explicit correction inside that rejected row window and authorize `resume_csv`.
The old rejected receipt must remain, the repaired attempt must get a new receipt
sequence/revision, earlier completed chunks must not replay, and a successful repair
must reduce unresolved `failed_rows` while increasing `corrected_rows` only for
changed rows that actually commit.

Calling the worker twice after an already completed session is focused coverage, not a
substitute for case A.

## 9. P11-REAL-IMPORT-RECEIPT

A completed or partial/repaired session must expose bounded inspectable evidence for:

```text
total_rows
imported_rows
failed_rows
corrected_rows
remaining_rows
duplicate_rows
planned_chunk_count
chunk_count
per-chunk row window
per-chunk imported/failed count
created record ids
receipt fingerprint
cleanup fingerprint when used
repair revision/fingerprint when used
```

Historical rejected receipts remain evidence even if a later repair succeeds and the
aggregate final `failed_rows` becomes zero.

## 10. Failure policy

If any gate fails:

1. record exact tested SHA and observed/expected behavior;
2. do not mark P11 accepted;
3. repair the smallest authoritative layer;
4. add deterministic regression coverage;
5. rerun the failed gate and direct neighbors;
6. never repair recovery by blindly replaying a chunk whose commit status is
   uncertain.

## 11. Acceptance boundary

The implemented P11 CSV core is not accepted until the focused gate and all six named
real gates execute successfully on the supported product path. Broader spreadsheet
formats, relational imports, external-id upserts and generic transformation scripting
are explicitly outside this acceptance boundary unless a HARD gate proves one is
required for the stated P11 product goal.

The acceptance evidence above was created only after the focused gate and all six real
gates executed successfully on the recorded environment and tested SHA.
