# Stabilization execution state

State format: 72
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

P11 remains the latest fully accepted phase. P12.1 has passed its focused authority
gate and is accepted as a Phase-12 slice; full P12 remains incomplete.

## Current cursor

```text
phase: 12
phase_name: controlled source-code modification
active_slice: P12.2-PROPOSED-PATCH-DIFF-CONTRACT
slice_state: READY_NOT_STARTED
current_gate_type: HARD_AUTHORITY_AND_DESIGN
blocking_implementation: P12.2 is not implemented; no typed workspace patch/diff capability or approved-diff fingerprint exists
blocking_validation: none for P12.1; P12 real gates remain pending until their corresponding P12.2-P12.4 contracts exist
latest_accepted_evidence: docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
latest_phase_acceptance: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_implementation_record: docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
latest_validation_record: docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
next_action: begin P12.2 by defining a typed proposed patch/diff contract restricted to the bound workspace, with exact before/after/diff fingerprints and no physical-path or free-form command input
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

## P12.1 validation and acceptance

Formal committed-SHA checks on `ad1378be0836fa3d49e4f24019288aa3a6e71b46`:

```text
python compileall                                      PASS
Ruff                                                   PASS
SourceWorkspaceTests                                   PASS — 10 tests
TestPhase12SourceWorkspace                             PASS — 3 methods / 0 failures / 0 errors
```

They cover Technical access, path-free installed-addon workspace preparation, source
freshness, non-Technical denial, cross-user denial, cross-turn denial, source
immutability, path/symlink/secret bounds and owner-bound cleanup.

P12.1 acceptance: **COMPLETE / P12.2 ELIGIBLE**.

Evidence:
`docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md`.

## Later Phase-12 real gates

All remain unexecuted:

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

P12.1 supplies the tested foundation for the first gate; P12.2-P12.4 must implement
the remaining contracts before any Phase-12 real gate can be claimed PASS.

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
docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
```
