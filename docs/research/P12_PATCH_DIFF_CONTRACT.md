# P12.2 typed proposed patch/diff contract

Date: 2026-09-03  
Status: **IMPLEMENTED / FOCUSED VALIDATION PENDING**

P12.1 established and validated the private workspace/source fingerprint boundary.
P12.2 adds the first executable source-edit surface, but it can mutate only a bound
private workspace. Installed/production source remains outside this effect.

## Capability surface

```text
assistant.source_workspace.prepare         PLAN / Technical
assistant.source_workspace.inspect         READ / Technical
assistant.source_workspace.read_file       READ / Technical
assistant.source_workspace.preview_patch   READ / Technical
assistant.source_workspace.apply_patch     PLAN / ACTION / POLICY / Technical
assistant.source_workspace.inspect_patch   READ / Technical
```

No capability accepts an absolute source/workspace path, command line, Git arguments,
Python code to execute or arbitrary filesystem-write target.

## Typed patch language

A proposal contains at most 12 logical files. Each item is exactly one of:

```text
modify: logical path + bounded exact old -> new replacements
create: logical path + bounded UTF-8 content
delete: logical path
```

`modify` requires each `old` fragment to occur exactly once in the current staged file.
Missing or ambiguous matches fail closed instead of applying a fuzzy patch to the wrong
location. Patchable file suffixes are a finite source/text allowlist; VCS, cache,
runtime and secret-like paths are denied.

## Fingerprint chain

Every preview binds:

```text
source baseline fingerprint
current parent workspace fingerprint
normalized typed changes
after workspace fingerprint
complete unified diff fingerprint
approval fingerprint
```

The complete approval diff is capped at 48 KiB. If it exceeds the bound the proposal
is rejected; the host never shows a truncated diff and then treats it as approval for
hidden changes.

## Apply semantics

Applying a patch recomputes the preview and stale checks. It does not edit the parent
workspace in place. Instead the host materializes a new derived workspace and persists
a private path-free patch receipt containing:

```text
child workspace id
parent workspace id
source fingerprint
before workspace fingerprint
after workspace fingerprint
diff fingerprint
approval fingerprint
binding fingerprint
changed logical paths
```

The parent stays intact as the reconstruction/rollback boundary. Neither parent nor
child is on Odoo's addons path and no installed source file is modified by P12.2.

## Hard bounds

```text
changed files                 12
edits per file                16
total edits                   48
one patchable file            512 KiB
aggregate proposal text       2 MiB
approval diff                 48 KiB
workspace file read           240 lines / 32 KiB
```

The existing P12.1 workspace ceilings remain authoritative above these narrower patch
limits.

## Deferred to P12.3/P12.4

P12.2 deliberately does not:

- run arbitrary tests or commands;
- declare a workspace deployable merely because a diff was approved;
- copy source into production;
- restart Odoo or update a module;
- authorize deployment from an untested fingerprint;
- implement host rollback after a production deployment.

P12.3 must produce an exact test receipt for the after-workspace fingerprint. P12.4
must separately cross the managed production source/maintenance boundary and reject a
stale installed source baseline.

## Focused validation

Prepared dependency-light coverage:

```text
tests/unit/test_phase12_source_patch.py
```

Prepared Odoo coverage:

```text
TestPhase12SourcePatch
TestPhase12SourceWorkspace   # direct P12.1 neighbor after capability promotion
```

No P12.2 test or real gate is PASS until actually executed.
