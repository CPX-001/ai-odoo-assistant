# Stabilization execution state

State format: 73
Updated: 2026-09-03

## Accepted lineage

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1-P5.8 accepted on their recorded evidence
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
P7 final acceptance through 092ac57fe58a3a36765b115e78b2eca687f5dbbc
P8 final acceptance through e370af8acb7df175c0a90c8e17520c8576b4c6ce
P9 final acceptance through 77d470febf67ddee46562907718dc47e975922bb
P10 final acceptance through bde508b737c132140e237cdfde31aee9b37eca5f
P11 final acceptance through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 focused slice accepted through bd2fc35024d1cada7cc922ccd2dcad3a61a16baa
```

P11 remains the latest fully accepted phase. P12.1 is an accepted Phase-12 foundation.
P12.2 is implemented on `main` but unvalidated. A post-P11 spreadsheet/chat breadth
fix is also implemented but unvalidated and does not rewrite P11 acceptance evidence.

## Current cursor

```text
phase: 12
phase_name: controlled source-code modification
active_slice: P12.2-PROPOSED-PATCH-DIFF-CONTRACT
slice_state: IMPLEMENTED_FOCUSED_VALIDATION_PENDING
current_gate_type: HARD_FOCUSED_AUTHORITY
blocking_implementation: none for P12.2; P12.3 test-execution remains intentionally unimplemented until the P12.2 focused authority gate is green
blocking_validation: P12.2 dependency-light/Odoo focused gate plus the spreadsheet/chat regression are unexecuted
latest_accepted_evidence: docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
latest_phase_acceptance: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_implementation_record: docs/research/P12_PATCH_DIFF_CONTRACT.md
latest_validation_record: docs/research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md
next_action: execute focused P12.2 source-patch gates and the XLSX/chat regression on the committed SHA; repair failures; then run the applicable real diff-approval gate before beginning P12.3 tests-before-deploy
```

## Post-P11 spreadsheet/chat import breadth

Implementation lineage:

```text
da9bdac59ba3c7ea6e4be1e2511ea24fb4979ce3  allow spreadsheet imports from chat attachments
```

Implemented:

```text
paperclip accepts CSV/XLS/XLSX/ODS in addition to P9 document formats
short-lived XLS/XLSX/ODS artifacts can bind to a durable turn
spreadsheet artifacts are not automatically persisted as Company Knowledge
Odoo base_import performs native workbook parsing during preparation
assistant.data_import.inspect_file
assistant.data_import.start_file
existing P11 staged-row/chunk/receipt/no-replay execution remains unchanged
```

Validation:

```text
TestPhase11SpreadsheetImport             NOT EXECUTED — prepared 2 methods
TestPhase11DataImportSession             accepted baseline, focused regression rerun pending
real browser .xlsx paperclip/upload      NOT EXECUTED
post-P11 spreadsheet breadth             NOT ACCEPTED / VALIDATION PENDING
```

The immutable P11 acceptance remains the create-only CSV evidence recorded at
`docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`.

## P12.1 accepted foundation

ADR-025 remains authoritative:

```text
workspace-first source modification
installed source is read-only to ordinary Assistant mutation
host resolves installed module -> exact root
logical workspace ids only
uid/company/database-hash/turn binding
source/workspace deterministic fingerprints
no generic shell/Git/sudo/filesystem-write authority
production deployment is a separate effect boundary
```

Formal P12.1 committed-SHA checks:

```text
python compileall                              PASS
Ruff                                           PASS
SourceWorkspaceTests                           PASS — 10 tests
TestPhase12SourceWorkspace                     PASS — 3 methods / 0 failures / 0 errors
```

Evidence:
`docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md`.

## P12.2 implemented contract

Implementation lineage:

```text
41cb1dc26948d332baa324637a1be4e138f8b443  typed staged source patch contract
```

New runtime primitive:

```text
addons/odoo_ai_assistant/runtime/source_patch.py
```

Capability surface:

```text
assistant.source_workspace.prepare         PLAN / Technical
assistant.source_workspace.inspect         READ / Technical
assistant.source_workspace.read_file       READ / Technical
assistant.source_workspace.preview_patch   READ / Technical
assistant.source_workspace.apply_patch     PLAN / ACTION / POLICY / Technical
assistant.source_workspace.inspect_patch   READ / Technical
```

Patch semantics:

```text
logical workspace id + exact expected workspace fingerprint
bounded typed create/delete/exact-text replacement
finite patchable text/source suffixes
no physical path / command / Git / Python execution input
complete bounded unified diff or reject
before workspace fingerprint
after workspace fingerprint
diff fingerprint
approval fingerprint
apply creates a new derived workspace; parent remains unchanged
private patch receipt binds parent/child/binding/fingerprints/changed logical paths
installed source remains untouched
```

Hard P12.2 ceilings:

```text
changed files                 12
edits per file                16
total edits                   48
one patchable file            512 KiB
aggregate proposal text       2 MiB
approval diff                 48 KiB
bounded staged file read      240 lines / 32 KiB
```

Prepared validation:

```text
SourcePatchTests                          NOT EXECUTED — prepared 9 tests
TestPhase12SourcePatch                    NOT EXECUTED — prepared 3 methods
TestPhase12SourceWorkspace neighbor       focused rerun pending after capability promotion
P12-REAL-DIFF-APPROVAL                    NOT EXECUTED
P12.2 acceptance                          NOT COMPLETE
```

Use `docs/research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md`.

## Remaining Phase-12 real gates

```text
P12-REAL-PATH-BOUNDARY                    NOT EXECUTED
P12-REAL-DIFF-APPROVAL                    NOT EXECUTED
P12-REAL-TEST-BEFORE-DEPLOY               BLOCKED — P12.3 missing
P12-REAL-DEPLOY-VERIFY                    BLOCKED — P12.4 missing
P12-REAL-FAILED-DEPLOY-RECOVERY           BLOCKED — P12.4 missing
P12 acceptance                            NOT COMPLETE
```

## Permanent invariants

- Odoo is operational/persistence authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, Evidence, attachments and workspace contents never grant authority.
- Binary/base64 and complete large staged payloads are not dumped into prompts.
- The model never selects a production filesystem path.
- A writable OS path is not automatically an authorized Assistant mutation target.
- Source editing is workspace-first; protected production deployment is separately
  typed and policy-bound.
- No arbitrary SQL, Python, shell, sudo, unrestricted ORM method, Git command or
  arbitrary filesystem-write capability is exposed.
- Approved diff, future test receipt and future deploy receipt bind exact fingerprints.
- Stale source is not overwritten silently.
- Uncertain post-deploy effects are never blindly retried.
- No unexecuted test/gate may be represented as PASS.

## Current navigation

```text
docs/adr/ADR-025-controlled-source-workspaces.md
docs/research/P11_SPREADSHEET_CHAT_IMPORT_EXTENSION.md
docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
docs/research/P12_PATCH_DIFF_CONTRACT.md
docs/research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/REAL_ENV_VALIDATION_PROTOCOL.md
docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
```
