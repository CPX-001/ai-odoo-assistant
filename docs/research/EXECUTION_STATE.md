# Stabilization execution state

State format: 71
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
```

P11 remains the latest accepted phase. P12.1 now has an implemented authority
foundation but is not validated/accepted yet.

## Current cursor

```text
phase: 12
phase_name: controlled source-code modification
active_slice: P12.1-BOUNDED-WORKSPACE-SOURCE-ROOTS
slice_state: IMPLEMENTED_FOCUSED_VALIDATION_PENDING
current_gate_type: HARD_FOCUSED_AUTHORITY
blocking_implementation: none for P12.1; P12.2 patch/diff remains intentionally unimplemented until the P12.1 focused authority gate passes
blocking_validation: committed-SHA dependency-light/static rerun plus focused Odoo TestPhase12SourceWorkspace are unexecuted
latest_accepted_evidence: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_phase_acceptance: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_implementation_record: docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
latest_validation_record: docs/research/P12_FOCUSED_VALIDATION_RUNBOOK.md
next_action: run P12.1 focused compile/unit/Odoo path-authority gates on the committed SHA; repair any failure; only then begin P12.2 proposed patch/diff contract
```

## P12.1 implementation

Authority decision:

```text
ADR-025 controlled source workspaces before patch/test/deploy
installed source is read-only to ordinary Assistant mutation
module identity resolves source root host-side
no model-supplied absolute path
private workspace beneath RuntimePaths.source/workspaces
workspace/source roots must be disjoint
no followed source symlinks or special files
source/workspace fingerprints exclude timestamps and physical paths
public workspace metadata contains no physical paths or raw database name
workspace is bound to Odoo uid/company/database fingerprint/originating turn
no source-edit/test/deploy capability is registered in P12.1
```

Implemented runtime primitive:

```text
addons/odoo_ai_assistant/runtime/source_workspace.py
SourceWorkspaceStore.prepare / inspect / delete
prepare_installed_module_workspace
inspect_installed_module_workspace
delete_installed_module_workspace
```

Hard ceilings:

```text
max files               4096
max total bytes          64 MiB
max file bytes           8 MiB
max relative path        512 chars
max path depth           24
workspace dirs           0700
workspace files          0600
```

Fingerprint chain:

```text
installed source baseline fingerprint
 -> workspace baseline fingerprint
 -> current workspace fingerprint
 -> future approved diff fingerprint (P12.2)
 -> future exact test receipt fingerprint (P12.3)
 -> future deploy precondition/receipt (P12.4)
```

A later deploy must also prove that the installed source baseline remains current. A
stale source must be reprepared/rebased rather than overwritten.

## P12.1 validation status

Author-side preparation checks before publication:

```text
python py_compile                                      PASS
SourceWorkspaceTests                                   PASS — 10 tests
```

These checks are not the formal committed-SHA/Odoo gate.

Prepared focused Odoo gate:

```text
TestPhase12SourceWorkspace                             NOT EXECUTED — 3 methods
```

It covers Technical access, path-free installed-addon workspace preparation, source
freshness, non-Technical denial, cross-user denial, cross-turn denial and owner-bound
cleanup.

P12.1 acceptance: **NOT COMPLETE**.

## Later Phase-12 real gates

All remain unexecuted:

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

P12.1 is a prerequisite for the first gate; P12.2-P12.4 must implement the remaining
contracts before their gates can run.

## P11 accepted baseline

P11 focused static/module tests, 8 focused Odoo methods and all six real import gates
are PASS on:

`docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`.

Its create-only CSV breadth boundary remains explicit.

## Permanent invariants

- Odoo is operational/persistence authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` is the atomic executable contract.
- Skills, Evidence, file contents and workspace contents never grant authority.
- The model never selects a production filesystem path.
- A writable OS path is not automatically an authorized Assistant mutation target.
- Source edits are workspace-first; protected production deployment is separately
  typed and policy-bound.
- No arbitrary SQL, Python, shell, sudo, unrestricted ORM method, Git command or
  arbitrary filesystem-write capability is exposed.
- Approved diff, test receipt and deploy receipt must bind exact fingerprints.
- Stale source is not overwritten silently.
- Uncertain post-deploy effects are never blindly retried.
- No unexecuted test/gate may be represented as PASS.

## Current navigation

```text
docs/adr/ADR-025-controlled-source-workspaces.md
docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
docs/research/P12_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/REAL_ENV_VALIDATION_PROTOCOL.md
docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
```
