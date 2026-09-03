# Odoo AI Assistant addon

The supported product is an Odoo 18 Community addon with an embedded durable
provider-neutral agent runtime. The browser talks to authenticated Odoo routes; Codex
App Server is an ephemeral reasoning-provider subprocess, not a product daemon.

## Current state

```text
P0-P11 COMPLETE / ACCEPTED
P12.1 BOUNDED SOURCE WORKSPACES FOCUSED ACCEPTED / P12.2 ELIGIBLE
P12 NOT ACCEPTED
```

The current addon version is `18.0.13.33.0`. Use
`../../docs/research/EXECUTION_STATE.md` for the exact cursor.

## Authority model

Odoo owns identity, companies, ACLs, record rules, capability availability, policy,
approval, persistence, execution and verification. Normal business operations use the
effective user's Environment with `su=False`.

`CapabilityDefinition` remains the atomic executable contract. Skills, Context,
Evidence, retrieved source/documents and file/workspace contents cannot grant
permissions. No arbitrary SQL, Python, shell, sudo or unrestricted Odoo method surface
is exposed.

Public human profiles are exactly `user` and `technical`; autonomy is independent from
technical reach.

## Accepted subsystems

- durable conversations/turn queue, concurrency, recovery, streaming and interventions;
- provider-neutral planning with TaskPlan/EffectPlan and EffectJournal;
- CapabilityProvider/Skill/Context/Evidence extension framework;
- runtime/source/XML/log Evidence and Odoo-native company Knowledge;
- optional finite P10 AF_UNIX Technical host broker and lifecycle-safe module update;
- durable P11 CSV imports with staging, chunk receipts, cleanup and repair/resume.

P11 is accepted through
`../../docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`.

## P12.1 source-workspace foundation

`runtime/source_workspace.py` implements a Technical-only host adapter that resolves an
installed addon by logical module name and copies a bounded snapshot into the private
Assistant runtime source tree. It returns logical workspace/source identities and
content fingerprints without exposing physical addon/data-dir paths or raw database
names.

The workspace is bound to the current user/company/database fingerprint/turn and
rejects path overlap, symlinks, special files, malformed ids and configured size/count
ceilings. Installed source is not mutated by this workflow.

P12.1 intentionally registers no model-callable source edit/test/deploy capability.
Future P12 work must proceed as workspace diff/patch -> exact-fingerprint tests ->
separately authorized deploy/verify/recovery. Protected production deployment remains
behind ADR-024 or an equivalently narrow finite host adapter, never generic shell/Git.

Focused compile/Ruff, all 10 dependency-light workspace tests and the 3-method Odoo
P12.1 authority gate pass on `ad1378b`; P12.2 is now eligible. This does not authorize
production source mutation or accept full Phase 12.

See:

```text
../../docs/adr/ADR-025-controlled-source-workspaces.md
../../docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
../../docs/research/P12_FOCUSED_VALIDATION_RUNBOOK.md
../../docs/research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md
```
