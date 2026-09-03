# ADR-025 — Controlled source workspaces before patch/test/deploy

Status: Accepted  
Proposed: 2026-09-03  
Accepted: 2026-09-03

## Context

Phase 11 is accepted. Phase 12 may eventually let a Technical user ask the Assistant
to modify Odoo addon source, but source modification is qualitatively different from
ordinary ORM writes or P10 host diagnostics. A bug, path escape or stale patch can
change executable code for every user and may require service/module lifecycle work.

The current product already has two relevant boundaries:

- P8 source Evidence resolves **installed addon names** to host-owned source roots and
  exposes only logical module-relative locators plus fingerprints; and
- ADR-024 permits finite privileged host operations through a separate broker instead
  of giving Odoo a general shell or root filesystem authority.

The Phase-12 roadmap requires:

```text
P12.1 bounded workspace/source roots + fingerprints
P12.2 proposed patch/diff contract
P12.3 tests before deployment
P12.4 deploy + verification + explicit recovery/rollback boundary
```

The first decision must therefore prevent a future patch capability from becoming a
model-authored filesystem editor.

## Decision

Source modification is **workspace-first**. The ordinary Odoo Assistant process may
read an eligible installed addon and copy a bounded snapshot into a private workspace,
but it does not directly mutate the installed/production source root.

```text
installed addon source (read-only authority)
        |
        | host resolves module -> exact installed root
        | bounded regular-file snapshot
        v
<data_dir>/odoo_ai_assistant/source/workspaces/<host id>/
        |
        | future P12.2 patch only here
        | future P12.3 tests only against this staged tree
        v
approved/tested workspace
        |
        | future typed deployment adapter
        v
managed source target -> module/service lifecycle -> verify
```

A filesystem being writable by the Odoo OS user does **not** make direct production
source mutation an accepted operation. Deployment is a separate effect boundary.

## Source-root authority

The model never provides an absolute path. Host code reuses the installed-source
semantics already used by `assistant.installed_source`:

1. require the Technical product boundary (`base.group_system` today);
2. resolve installed modules from the effective Odoo registry;
3. resolve the module path through Odoo's module/addons-path machinery;
4. canonicalize the root host-side;
5. reject unavailable roots, symlink roots and workspace/source overlap.

Only installed addon modules are eligible in P12.1. Repository acquisition and
promotion remain separate future workflows.

Physical addon/data-dir paths are host-internal. Model-visible workspace metadata uses
logical identities such as:

```text
source_id:     odoo-addon:<module>
workspace_id:  workspace:v1:<host-generated-uuid>
```

## Workspace binding

A workspace is not transferable merely because another Technical user learns its id.
Its metadata stores an opaque canonical binding fingerprint derived from:

```text
Odoo uid
company id
hashed database identity
originating turn id
```

The raw database name and physical source/workspace paths are not part of the public
workspace projection. Every later inspect/patch/test/deploy operation must rebind the
workspace to the current host context before use.

## Snapshot and fingerprint contract

P12.1 computes a deterministic SHA-256 snapshot fingerprint over a sorted manifest of
copied files:

```text
logical relative path
byte size
file SHA-256
```

The fingerprint excludes timestamps and physical paths. It therefore supports:

- precondition binding;
- stale-source detection;
- workspace-change detection;
- diff/test/deploy receipt chaining;
- deterministic replay checks without leaking host layout.

The baseline source fingerprint and current workspace fingerprint are separate. A
workspace may become intentionally different after P12.2 while the installed source
must still match its baseline before deployment.

## Filesystem boundary

The reference workspace store is stdlib-only and bounded:

```text
workspace parent mode          0700
workspace directory mode       0700
workspace files                0600
maximum files                  4096
maximum total copied bytes     64 MiB
maximum one file               8 MiB
maximum relative path          512 chars
maximum relative depth         24
```

The store:

- never follows source symlinks;
- rejects special/non-regular files;
- rejects `..`, absolute paths and reserved metadata names;
- ignores VCS/cache/vendor/runtime directories that should not enter a patch
  workspace;
- excludes obvious secret/private-key filenames from the source snapshot;
- treats secret-named files appearing inside a workspace as tampering rather than
  silently hiding them;
- writes into a same-parent pending directory and publishes it by atomic rename;
- deletes only ids that resolve beneath the managed workspace root.

These are ceilings, not permission grants. Later patchable file types will be narrower
than the set of regular files copied for testing fidelity.

## No production mutation in P12.1

P12.1 intentionally exposes **no source-edit, patch, test-execution or deployment
capability**. It only establishes the host-owned workspace primitive and Odoo adapter
needed by later slices.

P12.2 may mutate only the bound workspace. It must not accept a physical path or
arbitrary patch command.

P12.3 must bind its test receipt to the exact workspace fingerprint that was tested.
A passing test for fingerprint A cannot authorize deployment of fingerprint B.

P12.4 deployment must be a separately typed effect. For host-managed production source
roots it should extend the ADR-024 broker/maintenance boundary or another equivalently
narrow deployment adapter. It must not become `shell`, `git <free form>`, `cp -r`,
`sudo` or arbitrary filesystem write exposed to the model.

## Deployment preconditions for later slices

Before any future deployment can cross the production source barrier, host code must
prove at minimum:

```text
workspace binding valid
baseline source fingerprint still current
approved diff fingerprint matches current workspace
required tests passed for that exact workspace fingerprint
managed deployment target is policy-resolved
recovery/rollback class is known before the effect barrier
```

If source changed after workspace creation, the deployment is stale and must be
reprepared/rebased rather than silently overwriting newer code.

Transport or lifecycle uncertainty after a deployment barrier follows the same rule as
ADR-024: it is not permission for a blind retry.

## Alternatives rejected

### Edit installed addon files directly from Odoo

Rejected. It collapses staging, approval, test and deployment into one write and makes
path bugs or stale assumptions production effects.

### Generic shell/git/Python capability

Rejected. A command interpreter is broader than the intended source-modification
contract and would bypass typed path, diff, test and recovery authority.

### Let the model choose an absolute source/workspace path

Rejected. Installed module identity and deployment policy resolve paths host-side.

### Use Codex provider workspace as source authority

Rejected. Provider process state is disposable and is not the Odoo/host persistence or
permission boundary.

### Make every production source root Odoo-writable to simplify deployment

Rejected. Convenience is not a reason to enlarge the ERP process's host authority.

## External/reference patterns considered

Odoo 18 resolves modules from configured addons paths and recommends updating/testing
custom module source before production upgrades. Odoo's testing framework provides
module-level Python/JS/tour validation, while its upgrade documentation emphasizes a
test environment before production changes. These reinforce a staged source -> test ->
deploy lifecycle, but they do not determine this project's authority model.

Project architecture research also recommends source editing in staging followed by
tests and controlled deployment. That material is design evidence; current code and
this ADR remain the authority.

## Consequences

- P12.2 gains a stable safe workspace identity instead of a filesystem path.
- P12.3 can prove exactly which source state was tested.
- P12.4 can reject stale production roots before deployment.
- Physical source/workspace paths remain host-internal.
- Large source trees may be rejected by bounded ceilings rather than silently copied.
- P12.1 alone gives the model no new write authority.

## Validation

P12.1 requires focused dependency-light and Odoo tests for path/root bounds, symlinks,
source immutability, fingerprints, Technical gating, user/turn binding and cleanup.
The five named P12 real gates remain mandatory as their corresponding patch/test/deploy
slices become executable.
