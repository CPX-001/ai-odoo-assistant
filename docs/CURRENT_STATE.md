# Current implementation state

This is the current-state entry point for the supported Odoo 18 product on `main`.
For the exact roadmap cursor and validation truth use
[`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Accepted lineage

```text
P0-P11 COMPLETE / ACCEPTED
P11 accepted through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 BOUNDED SOURCE WORKSPACES FOCUSED ACCEPTED / P12.2 ELIGIBLE
P12 NOT ACCEPTED
```

P11 remains the latest fully accepted phase. P12.1 has passed its focused authority
gate and establishes the source/workspace boundary required before patch/test/deploy;
it does not expose production source editing.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported addon: `addons/odoo_ai_assistant`.
- Current addon version: `18.0.13.33.0`.
- Dependencies: `account`, `base`, `base_import`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Business capabilities execute under the effective Odoo user with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Codex App Server is the current ephemeral reasoning provider, not product authority.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM-method surface is exposed.

Product-facing human profiles remain exactly `user` and `technical`. Autonomy never
creates permissions or enlarges the P10 broker/P12 filesystem authority boundary.

## Durable agent, Evidence and Knowledge

Accepted P5-P7 provide durable turns, concurrency/recovery, TaskPlan vs EffectPlan,
EffectJournal, interventions, provider-neutral decisions and the installed-addon
Capability/Skill/Context/Evidence extension framework.

Accepted P8 provides bounded provenance/freshness/access-aware runtime, source/XML and
log Evidence. Accepted P9 provides Odoo-native company Knowledge with bounded document
ingestion, PostgreSQL lexical FTS, citations and stale-reference handling. Retrieved or
uploaded text is untrusted data and cannot grant executable authority.

## Accepted P10 Technical/host operations

Technical operations include `odoo.module.inspect`, `postgres.health`, managed config
inspect/patch, service status/restart and lifecycle-safe module update. ADR-024 governs
the optional AF_UNIX broker with deployment-owned logical targets, peer credentials,
fixed argv, durable effect receipts and explicit uncertainty. The broker is not a
shell, a third human profile or the Assistant runtime.

## Accepted P11 advanced imports

P11 implements durable create-only CSV workflows instead of thousands of ordinary CRUD
tool calls. It includes mapped-row staging, bounded background chunks, exact receipts,
no-blind-replay recovery, deterministic cleanup and explicit rejected-window
repair/resume under the originating effective user.

P11 focused tests and all six named real gates are PASS on the accepted evidence at:
`research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`.

## P12.1 controlled source workspace — focused accepted

ADR-025 establishes a workspace-first source-modification boundary.

Current P12.1 code may copy a bounded snapshot of one installed Odoo addon into:

```text
<data_dir>/odoo_ai_assistant/source/workspaces/<host-generated-id>/
```

The model never chooses an absolute source/workspace path. Host code reuses the
installed-source resolver to map an installed module name to its effective addon root.
The source root is treated as read-only by this workflow even when the Odoo OS account
could technically write it.

The workspace contract provides:

```text
source_id = odoo-addon:<module>
workspace_id = workspace:v1:<32hex>
private 0700 directories / 0600 files
no followed symlinks
no source/workspace-root overlap
bounded regular-file snapshot
4096 file ceiling
64 MiB total ceiling
8 MiB single-file ceiling
canonical source/workspace SHA-256 fingerprints
separate source-stale vs workspace-changed state
opaque user/company/database/turn binding fingerprint
path-free public metadata
bounded owner-bound deletion
```

Physical addon roots, `data_dir`, workspace paths and raw database names are not part
of the public projection.

P12.1 deliberately registers **no** source-edit, patch, test-execution or deploy
capability. Future slices must compose through the same boundary:

```text
P12.2 explicit workspace diff/patch contract
P12.3 tests bound to exact post-patch workspace fingerprint
P12.4 separately typed deploy + verification + recovery boundary
```

A future protected-source deployment must use ADR-024's finite broker pattern or an
equivalently narrow deployment adapter. Generic shell/Git/sudo/arbitrary filesystem
write remains outside the product contract.

## P12.1 validation truth

Formal committed-SHA validation executed:

```text
compileall + focused Ruff                           PASS
SourceWorkspaceTests                               PASS — 10 tests
TestPhase12SourceWorkspace                         PASS — 3 methods
```

P12.1 is accepted on
`research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md`. P12.2 is eligible;
the immediate next action is to define a typed workspace-only proposed patch/diff
contract with exact before/after fingerprints and no physical-path or free-form command
input.

The later Phase-12 real gates remain unexecuted:

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```
