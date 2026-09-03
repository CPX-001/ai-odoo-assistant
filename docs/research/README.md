# Research and execution guidance

This directory contains roadmap state, implementation records, validation runbooks and
immutable evidence. Current code plus accepted ADRs outrank dated research.

## Current cursor

```text
P0-P11 COMPLETE / ACCEPTED
P11 accepted through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 BOUNDED SOURCE WORKSPACES IMPLEMENTED
P12.1 FOCUSED ODOO VALIDATION PENDING
P12 NOT ACCEPTED
```

Use `EXECUTION_STATE.md` for exact lineage, blockers and next action.

## Primary current records

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Exact roadmap cursor and validation truth. |
| `P12_SOURCE_WORKSPACE_FOUNDATION.md` | P12.1 source/workspace identity, bounds and no-production-mutation contract. |
| `P12_FOCUSED_VALIDATION_RUNBOOK.md` | Focused P12.1 gate and five later Phase-12 real gates. |
| `../adr/ADR-025-controlled-source-workspaces.md` | Accepted P12 staging/path/fingerprint authority decision. |
| `P11_IMPORT_CLEANUP_REPAIR_SLICE.md` | Latest accepted P11 implementation record. |
| `evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md` | P11 immutable acceptance. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named real product-path gates. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Expensive broad regression when explicitly required. |

## P12 authority direction

```text
installed addon source (read-only to ordinary Assistant mutation)
 -> host-resolved bounded private workspace
 -> explicit approved diff/patch
 -> tests bound to exact workspace fingerprint
 -> separately typed deploy
 -> verify / recovery
```

P12.1 provides only the first arrow. It exposes no filesystem editor, patch executor,
test command or deployment effect to the model.

The source/workspace foundation reuses P8 installed-source resolution and the private
runtime source area. A future protected deploy must use ADR-024's finite broker model
or an equivalently narrow deployment adapter; generic shell/Git/sudo remains forbidden.

## P12 validation truth

Author-side dependency-light preparation currently records 10 workspace tests PASS and
Python compilation PASS. The focused Odoo 3-method authority test is prepared but not
executed. Therefore P12.1 remains validation pending and P12.2 is blocked by the active
HARD focused gate.

Later HARD real gates remain:

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

## Execution rule

Every continuation reconstructs from Git:

```text
inspect main + AGENTS.md + EXECUTION_STATE
 -> process new gate evidence first
 -> repair failed HARD gate if present
 -> otherwise execute the exact next slice
 -> update code/tests/docs/evidence coherently
```

No GitHub Actions are used for this roadmap while repository policy says runners are
unavailable. Unexecuted validation is never PASS.
