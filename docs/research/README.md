# Research and execution guidance

This directory contains roadmap state, implementation records, validation runbooks and
immutable evidence. Current code plus accepted ADRs outrank dated research.

## Current cursor

```text
P0-P11 COMPLETE / ACCEPTED
P12.1 BOUNDED SOURCE WORKSPACES FOCUSED ACCEPTED
P12.2 TYPED PATCH/DIFF IMPLEMENTED / FOCUSED VALIDATION PENDING
P12 NOT ACCEPTED
post-P11 spreadsheet/chat breadth IMPLEMENTED / VALIDATION PENDING
```

Use `EXECUTION_STATE.md` for exact lineage, blockers and next action.

## Primary current records

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Exact roadmap cursor and validation truth. |
| `P11_SPREADSHEET_CHAT_IMPORT_EXTENSION.md` | Post-P11 XLS/XLSX/ODS chat/import breadth and focused debt. |
| `P12_SOURCE_WORKSPACE_FOUNDATION.md` | Accepted P12.1 source/workspace identity and bounds. |
| `P12_PATCH_DIFF_CONTRACT.md` | Implemented P12.2 typed private-workspace edit/diff contract. |
| `P12.2_FOCUSED_VALIDATION_RUNBOOK.md` | Immediate P12.2 + spreadsheet regression gate. |
| `P12_FOCUSED_VALIDATION_RUNBOOK.md` | Executed P12.1 gate and Phase-12 real-gate names. |
| `evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md` | P12.1 focused authority acceptance. |
| `../adr/ADR-025-controlled-source-workspaces.md` | Accepted P12 staging/path/fingerprint authority decision. |
| `evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md` | Immutable accepted P11 CSV evidence. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named real product-path gates. |

## P12 authority direction

```text
installed addon source (read-only to ordinary Assistant mutation)
 -> host-resolved bounded private workspace                 P12.1 accepted
 -> typed approved diff + derived workspace                P12.2 implemented
 -> tests bound to exact workspace fingerprint             P12.3 pending
 -> separately typed deploy -> verify / recovery           P12.4 pending
```

P12.2 still does not grant production source write, generic filesystem access, shell,
Git or arbitrary command execution. A protected deploy must use ADR-024's finite
broker model or an equivalently narrow adapter.

## Current validation truth

P12.1 committed-SHA compile/Ruff, 10 dependency-light workspace tests and 3 focused
Odoo methods passed. P12.2 has 9 dependency-light and 3 Odoo methods prepared but not
executed. The spreadsheet/chat extension has 2 focused Odoo methods prepared plus a
required real composer `.xlsx` check; none is represented PASS yet.

Later HARD Phase-12 gates remain:

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

No GitHub Actions are used while repository policy says runners are unavailable.
Unexecuted validation is never PASS.
