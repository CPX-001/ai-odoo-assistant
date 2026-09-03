# Research and execution guidance

This directory contains implementation records, validation runbooks, product-eval
specifications and immutable evidence. Research history does not override current code
or accepted ADRs.

## Authority

When sources disagree, normally prefer:

1. current code on `main` plus accepted ADRs;
2. current architecture/subsystem docs;
3. current tests and accepted real evidence;
4. `EXECUTION_STATE.md` and the active phase record;
5. older reports/external references.

Unexecuted validation is never PASS.

## Current cursor

```text
P0-P10 COMPLETE / ACCEPTED
P10 latest accepted phase at bde508b737c132140e237cdfde31aee9b37eca5f
P11 ADVANCED IMPORTS CSV CORE IMPLEMENTED
P11 DETERMINISTIC CLEANUP + REPAIR/RESUME IMPLEMENTED
P11 FOCUSED + REAL VALIDATION PENDING
P11 NOT ACCEPTED
```

Use `EXECUTION_STATE.md` for exact lineage, blockers, gates and next action.

## Primary current documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Exact roadmap cursor, validation truth and next action. |
| `P11_ADVANCED_IMPORTS_FIRST_SLICE.md` | Durable CSV artifact/staging/chunk contract. |
| `P11_IMPORT_CLEANUP_REPAIR_SLICE.md` | Deterministic cleanup and rejected-window repair/resume contract. |
| `P11_FOCUSED_VALIDATION_RUNBOOK.md` | Focused and six HARD real P11 gates. |
| `P10_HOST_OPERATIONS_FIRST_SLICE.md` | Accepted Technical/broker implementation record. |
| `P10_FOCUSED_VALIDATION_RUNBOOK.md` | Executed P10 validation contract. |
| `P9_KNOWLEDGE_FIRST_SLICE.md` | Accepted P9 Knowledge record. |
| `P8_EVIDENCE_CORE_IMPLEMENTATION.md` | Accepted P8 Evidence record. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable execution/validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named real Odoo/provider/host/browser gates. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Expensive broad regression when required. |
| `PRODUCT_BEHAVIOR_EVALS_V1.md` | Permanent product-behavior baseline. |

Older preparation records are historical rather than the current cursor.

## Current architecture lineage

Accepted P7 provides installed-addon `CapabilityProvider`, Skills, ContextProviders,
effective manifests and progressive disclosure. Accepted P8/P9 extend the same seam
with Evidence and Knowledge. Accepted P10 adds the typed Technical host boundary and
external lifecycle-safe module update.

P11 reuses those contracts rather than adding another tool registry or queue system:

```text
current-turn bounded artifact ref
 -> Odoo base_import inspection
 -> host-filtered direct scalar mapping
 -> staged mapped rows + fingerprints
 -> PLAN/policy
 -> durable ir.cron chunks under effective user, su=False
 -> per-chunk receipts
 -> finite deterministic cleanup when proposed
 -> bounded rejected-window inspection
 -> explicit mapped-row repair + resume from committed cursor
```

Current P11 capability surface:

```text
assistant.data_import.inspect_csv
assistant.data_import.start_csv
assistant.data_import.status
assistant.data_import.inspect_cleanup
assistant.data_import.start_clean_csv
assistant.data_import.inspect_rejected
assistant.data_import.resume_csv
```

Cleanup is limited to `trim`, `normalize_whitespace`, `replace_exact` and
`set_if_empty` over already-mapped fields. Repair accepts only explicit row + mapped
field + replacement value inside the current rejected window. Neither creates new
execution authority.

## Validation truth

P10 acceptance evidence remains immutable at:

`evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md`

P11 currently has 8 prepared focused Odoo methods across:

```text
TestPhase11DataImportSession
TestPhase11DataImportCleanupRepair
```

None has been executed in the supported Odoo environment in this ChatGPT run. The six
HARD real gates are also unexecuted:

```text
P11-REAL-CSV-IMPORT
P11-REAL-LARGE-IMPORT
P11-REAL-MAPPING-CORRECTION
P11-REAL-PARTIAL-INVALID
P11-REAL-RESUME-NO-DUPLICATE
P11-REAL-IMPORT-RECEIPT
```

Full repository/addon/HOOT/Product Behavior regression remains periodic debt unless a
focused failure or explicit instruction widens scope.

## Accepted evidence anchors

```text
P5.8 evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
P7 acceptance evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md
P8 acceptance evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
P9 acceptance evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md
P10 acceptance evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md
```

Historical blocker/focused records are not rewritten after later acceptance.

## External references

External projects are design references, not requirements. Relevant patterns include
Odoo native import/lifecycle behavior, OCA asynchronous import chunking, Pydantic AI
progressive disclosure, FastMCP/provider composition, Apexive/OCA reusable tools,
ERPipe typed writes and Linux/systemd hardening. The project keeps its stronger
Odoo/host authority boundary and does not add a framework or shell merely to resemble
a reference.

## Execution rule

Every future run reconstructs from Git:

```text
inspect current main
 -> read EXECUTION_STATE + active implementation records
 -> process new validation evidence first
 -> repair failed HARD gate if present
 -> otherwise follow exact next action
 -> update code/tests/docs/evidence coherently
```

Repository policy does not use GitHub Actions as the roadmap validation path.
