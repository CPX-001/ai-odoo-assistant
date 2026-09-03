# P12.1 — bounded source-workspace foundation

Date: 2026-09-03  
Status: **IMPLEMENTED / FOCUSED ACCEPTED / P12.2 ELIGIBLE**

P11 is accepted. This record covers only the Phase-12 authority prerequisite for
controlled source modification. It does **not** expose source editing, patching, test
execution or production deployment to the model.

## Goal

Create a host-owned staging boundary that later P12 slices can safely compose as:

```text
installed addon source
 -> bounded immutable baseline snapshot
 -> private Assistant workspace
 -> future typed diff/patch
 -> future tests bound to exact workspace fingerprint
 -> future separately authorized deploy + verify/recovery
```

The ordinary Odoo process never receives a generic filesystem editor, shell or Git
command surface.

## Reused current architecture

P12.1 extends existing seams instead of adding a new runtime:

- `assistant.installed_source` already resolves installed addon names to host-owned
  module roots and uses logical module-relative source identity;
- `RuntimePaths.source` provides a private Odoo-owned mutable runtime area under the
  configured `data_dir`;
- `CapabilityDefinition`/EffectPlan remains the future executable authority boundary;
- ADR-024 remains the required pattern when a future production deploy genuinely
  crosses a protected host/filesystem/service boundary.

Odoo 18 itself resolves modules from configured addon paths. External Odoo guidance
also strongly favors testing custom-module changes before production; this supports
staging-first execution but does not replace this project's host authority model.

## Implemented filesystem primitive

New runtime module:

```text
addons/odoo_ai_assistant/runtime/source_workspace.py
```

The stdlib-only `SourceWorkspaceStore` provides bounded prepare/inspect/delete
operations. Odoo-specific adapters are lazy and require the current Technical boundary
(`base.group_system`).

Workspace layout:

```text
<data_dir>/odoo_ai_assistant/source/workspaces/<32-hex-id>/
```

Public logical identities are:

```text
source_id:    odoo-addon:<module>
workspace_id: workspace:v1:<32hex>
```

Physical source roots, addon paths, `data_dir` and raw database names are never part of
public workspace metadata.

## Source and path authority

The model never supplies an absolute source path. The Odoo adapter:

1. checks Technical access;
2. resolves currently installed modules through the existing P8 source-evidence
   resolver/Odoo module machinery;
3. canonicalizes the source root host-side;
4. rejects source-root symlinks and source/workspace overlap;
5. copies only bounded regular files without following symlinks.

The workspace parent and directories are mode `0700`; copied files and metadata are
mode `0600`. Publishing uses a same-parent pending directory followed by atomic rename
and directory fsync.

Current hard ceilings:

```text
files/session            4096
copied bytes/session      64 MiB
single file               8 MiB
relative path             512 characters
relative depth            24 components
```

VCS/cache/runtime directories are excluded. Obvious secret/private-key filenames are
excluded from the source snapshot; a secret-named entry appearing later inside the
managed workspace is treated as tampering and inspection fails closed.

## Binding and fingerprints

Each workspace stores only an opaque binding fingerprint derived from:

```text
Odoo uid
current company id
SHA-256(database name)
originating turn id
```

A different user, database/company context or turn cannot reuse the workspace simply
by learning its id.

The baseline snapshot fingerprint is canonical SHA-256 over sorted tuples of:

```text
logical relative path
byte size
file SHA-256
```

Timestamps and physical paths are deliberately excluded. Inspection reports separately:

- whether the installed source is stale relative to the baseline; and
- whether the private workspace has changed relative to that baseline.

This creates the precondition chain required by future P12.2-P12.4 diff/test/deploy
receipts.

## No production mutation

P12.1 registers **no** model-callable source-edit capability. It also does not execute
tests or deploy files.

Future boundaries are fixed by ADR-025:

```text
P12.2 patch/diff -> bound workspace only; no physical path/free-form command
P12.3 tests      -> PASS receipt bound to exact workspace fingerprint
P12.4 deploy     -> separately typed effect + current source precondition + verify/recovery
```

For protected production roots, deployment should extend ADR-024's finite broker or an
equivalently narrow deployment adapter. Direct production `shell`, arbitrary `git`,
`sudo`, `cp -r` or arbitrary filesystem write remain forbidden.

## Validation truth

Formal checks executed on committed SHA
`ad1378be0836fa3d49e4f24019288aa3a6e71b46`:

```text
python compileall                                     PASS
Ruff                                                  PASS
SourceWorkspaceTests                                  PASS — 10 tests
TestPhase12SourceWorkspace                            PASS — 3 methods
```

P12.1 focused acceptance is recorded at
`evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md`. This accepts only the bounded
workspace foundation. P12.2 may now begin, but no source-edit capability exists yet.
