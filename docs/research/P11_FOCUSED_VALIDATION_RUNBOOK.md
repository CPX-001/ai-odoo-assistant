# P11 focused validation runbook

State: `READY / NOT EXECUTED`  
Scope: first durable create-only CSV import session slice

Implementation record: `P11_ADVANCED_IMPORTS_FIRST_SLICE.md`.

This runbook is incremental. It does not authorize the full addon/repository/browser
regression unless a focused failure demonstrates a wider blast radius.

## 1. Focused static gate

On the exact current `main`, compile/lint at minimum:

```text
addons/odoo_ai_assistant/models/data_import.py
addons/odoo_ai_assistant/runtime/capabilities/providers/assistant_data_import.py
addons/odoo_ai_assistant/tests/test_phase11_data_import.py
addons/odoo_ai_assistant/models/__init__.py
addons/odoo_ai_assistant/tests/__init__.py
addons/odoo_ai_assistant/__manifest__.py
```

Also validate XML/CSV loading through the Odoo module update rather than treating text
syntax alone as enough:

```text
security/data_import_security.xml
security/ir.model.access.csv
data/data_import_cron.xml
```

## 2. Focused Odoo gate

Use Odoo 18 Community and a disposable database. Update the addon and run exactly:

```text
/odoo_ai_assistant:TestPhase11DataImportSession
```

Expected selector: **4 methods**.

Required properties:

- current-turn CSV inspection returns bounded columns/examples and only effective-user
  safe scalar import fields;
- start is idempotent for the same turn/artifact/model/mapping/chunk-size request;
- a 2-row fixture with `chunk_size=1` creates exactly two target records and two
  completed receipts;
- rerunning the worker after completion creates no duplicate record;
- an invalid second chunk leaves the first committed chunk/receipt intact and rejects
  the second chunk without writing its row;
- `company_id` or another host-blocked field cannot enter the final mapping;
- another user cannot inspect the originating turn/session;
- `assistant.data_import.start_csv` remains PLAN + policy-controlled + segmented and
  the READ capabilities remain read-only;
- target business writes execute under the recorded effective user with `su=False`.

If a failure touches shared capability-plan/recovery behavior, add only the necessary
direct neighbors, for example:

```text
TestCanonicalPlanHostLoop
TestEffectJournal
```

Do not widen automatically.

## 3. Real product-path fixtures

Use the normal browser/chat -> durable turn -> embedded runtime path with:

- one normal internal user with create access on the target fixture model;
- a second user for ACL denial;
- disposable records/database only;
- CSV attachments below the existing 8 MB attachment ceiling;
- one small fixture, one ambiguous-header fixture, one partial-invalid fixture and one
  realistically large fixture;
- a low chunk size for replay/interrupt testing where useful.

Record tested SHA, Odoo/PostgreSQL version, user/profile/autonomy, session uuid,
chunk size/counts, sanitized receipts and timing. Do not persist raw customer files or
provider-private reasoning as evidence.

## 4. P11-REAL-CSV-IMPORT

Attach a small CSV containing at least two contacts/fixture records.

Procedure:

1. ask the Assistant to inspect the file for the intended model;
2. confirm the proposed mapping uses only returned safe fields;
3. inspect the host preview including exact row count, duplicate count, mapping
   fingerprint and chunk size;
4. authorize according to current policy;
5. wait/poll through `assistant.data_import.status`;
6. verify created records and completed receipts.

Pass:

- exact intended records are created once;
- no ignored/protected column is written;
- final status reports matching imported/failed/remaining counts.

## 5. P11-REAL-LARGE-IMPORT

Use a realistically large disposable CSV, preferably at least several multiples of
the chosen chunk size.

Pass:

- the session advances through multiple durable chunks;
- ordinary Odoo navigation and an unrelated Assistant conversation remain usable;
- each worker transaction remains bounded;
- final imported count equals actual created records;
- there is no requirement to issue hundreds/thousands of individual CRUD tool calls.

Record per-chunk timing and total duration where available.

## 6. P11-REAL-MAPPING-CORRECTION

Use an ambiguous header such as a business-export label that does not exactly equal the
technical field name.

Pass:

- Odoo-native suggestion/examples give the model enough evidence to propose a map or
  ask a useful clarification;
- the model may correct/replace a suggestion;
- the host accepts only the final `column_index -> field` mapping if every field is in
  the effective safe-field set;
- hostile text inside a header/value cannot widen the mapping or model authority.

This gate tests mapping correction, not row-enrichment correction.

## 7. P11-REAL-PARTIAL-INVALID

Use at least two chunks where an earlier chunk is valid and a later chunk contains a
value rejected by Odoo validation.

Pass for the declared first-slice semantics:

- earlier valid chunk commits and has a completed receipt;
- the invalid chunk is dry-run rejected as a whole and writes zero rows;
- session becomes `partial`;
- imported, failed and remaining counts are exact for the processed/rejected windows;
- the Assistant does not claim row-level salvage that was not performed.

## 8. P11-REAL-RESUME-NO-DUPLICATE

Use `chunk_size` small enough to observe multiple transactions. After at least one
chunk has committed, interrupt/restart the worker/Odoo process before the whole import
finishes.

Pass:

- the durable session resumes from its committed `next_row`/chunk receipts;
- completed chunks are not executed again;
- a transaction interrupted before commit leaves neither imported rows nor a false
  completed receipt for that chunk;
- final target record count contains no duplicate caused by recovery.

Do not simulate success merely by calling the worker twice after a completed session;
that is focused coverage, not the real interruption gate.

## 9. P11-REAL-IMPORT-RECEIPT

Pass when the completed or partial session exposes inspectable, bounded evidence for:

```text
total_rows
imported_rows
failed_rows
corrected_rows
remaining_rows
duplicate_rows
chunk_count
per-chunk row window
per-chunk imported/failed count
created record ids
receipt fingerprint
```

`corrected_rows=0` is truthful for this first slice because row cleanup/enrichment is
not yet implemented.

## 10. Failure policy

If any focused or real gate fails:

1. record exact tested SHA and observed/expected behavior;
2. do not mark P11 accepted;
3. repair the smallest authoritative layer;
4. add deterministic regression coverage;
5. rerun the failed gate and direct neighbors;
6. never fix recovery by blindly replaying a chunk whose commit status is uncertain.

## 11. Acceptance boundary

The first slice can only become a validated **partial Phase-11 implementation** after
its applicable focused/real gates execute. Full P11 acceptance additionally requires
closing any product gaps exposed by the six HARD gates, including richer
cleanup/enrichment behavior if the real `P11-REAL-IMPORT-RECEIPT` contract requires
non-zero corrected-row semantics.

Do not create P11 acceptance evidence before actual execution.
