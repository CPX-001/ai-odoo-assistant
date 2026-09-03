# P11 import cleanup and repair slice

Date: 2026-09-03  
Status: **IMPLEMENTED / VALIDATION PENDING**

This record extends the durable CSV session from
`P11_ADVANCED_IMPORTS_FIRST_SLICE.md`. It is implementation documentation, not PASS
evidence.

## Goal

Close the main functional gap in the P11 roadmap pipeline between mapping and chunked
execution:

```text
inspect -> map -> validate -> detect duplicates/errors
 -> proposed cleanup/enrichment -> preview/policy
 -> durable chunks -> rejected-window repair/resume -> receipts
```

The model may propose corrections, but it does not receive a generic transformation
language or new write authority. The host accepts only finite deterministic cleanup
operations over fields already present in the validated mapping.

## Deterministic cleanup

New capabilities:

```text
assistant.data_import.inspect_cleanup   READ
assistant.data_import.start_clean_csv   PLAN / ACTION / POLICY
```

Supported rules are deliberately finite:

```text
trim
normalize_whitespace
replace_exact
set_if_empty
```

`trim` and `normalize_whitespace` are limited to mapped text-like fields.
`replace_exact` and `set_if_empty` still remain inside the existing mapped scalar field
ceiling and are validated again by Odoo during chunk import.

The cleanup preview exposes exact changed-row count, duplicate count before/after,
bounded before/after samples, mapping fingerprint and cleanup fingerprint. Raw binary
or the full staged table is not returned to the model.

A cleaned import stores the deterministic rules, the cleaned staged rows and the set of
changed row indices as host-owned data. `corrected_rows` increases only when a changed
row actually commits. A proposed cleanup that later fails Odoo validation is therefore
not falsely counted as a successful correction.

## Rejected-window inspection and repair

New capabilities:

```text
assistant.data_import.inspect_rejected  READ
assistant.data_import.resume_csv        PLAN / ACTION / POLICY
```

When a chunk is rejected, the Assistant may read only a bounded window from that
latest rejected chunk, and only values for fields already in the approved mapping.
It receives sanitized Odoo validation messages plus row numbers.

`resume_csv` accepts only explicit corrections of the form:

```text
row + mapped field + replacement value
```

Corrections must target the current rejected row window. The host revalidates the
current user, company, target model, field mapping and staged artifact before preparing
the repair.

The repair:

- preserves every earlier completed chunk and its receipt;
- preserves the rejected receipt as historical evidence;
- changes only the host-owned staged mapped rows for the rejected window;
- increments a monotonic repair revision and binds a repair fingerprint to the old
  rejected receipt plus before/after staged fingerprints;
- clears the aggregate failed-row count for the rows being explicitly retried;
- leaves `next_row` at the committed cursor, so the retry starts exactly at the
  rejected window rather than replaying earlier successful chunks;
- authorizes a new receipt sequence for the retry and remaining chunks;
- re-enters the same bounded cron worker and effective-user `su=False` execution path.

If the repaired chunk fails again, it produces another rejected receipt and may be
repaired again through another explicit PLAN effect. There is no automatic blind retry.

## Correction receipt semantics

The session now distinguishes:

```text
planned_corrected_rows  rows whose staged mapped values differ from the original map
corrected_rows          changed rows that actually committed successfully
repair_revision         number of accepted repair/resume mutations
```

Historical rejected receipts remain visible even when a later correction succeeds.
Consequently the final aggregate `failed_rows` may be zero while the receipt history
still proves that an earlier attempt was rejected. This is intentional provenance, not
a contradiction.

## Authority and safety

Cleanup and repair do not add any model, field or relational authority. They reuse:

- current-turn artifact binding for new imports;
- owner/company binding for durable sessions;
- `agent_model_is_eligible()`;
- effective-user create access;
- `visible_action_preview_fields()`;
- direct scalar mapping limits;
- PLAN policy/approval;
- durable segmented receipts and the existing cron transaction boundary.

There is no arbitrary Python, expression evaluator, SQL, shell, ORM method name,
relational path, external-id update or generic transformation DSL.

## Still deferred breadth

The implemented P11 core remains intentionally create-only CSV. The following are not
claimed by this slice:

```text
XLS/XLSX/ODS durable sessions
relational field paths
external-id update/upsert
arbitrary row scripts or expressions
automatic semantic/entity matching across existing Odoo records
automatic final chat turn spawned by background completion
```

Those are later breadth decisions and are not required to pretend that the current
safe CSV workflow is complete.

## Validation truth

Focused tests are prepared for deterministic cleanup, authority denial, rejected-row
inspection, repair/resume, corrected-row accounting, receipt preservation and
capability metadata. They have not been executed in the supported Odoo 18 environment
in this ChatGPT run.

P11 remains **VALIDATION PENDING** until the focused gate and the six named real gates
in `P11_FOCUSED_VALIDATION_RUNBOOK.md` execute successfully. No P11 PASS or acceptance
is asserted here.
