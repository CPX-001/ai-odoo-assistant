# Architecture

Current architecture for `CPX-001/ai-odoo-assistant`. Current code plus accepted ADRs
are authoritative; `CURRENT_STATE.md` summarizes implementation and
`research/EXECUTION_STATE.md` owns roadmap/validation truth.

## Deployment units

The supported product is an Odoo 18 Community addon with an embedded durable agent
runtime:

```text
Browser / OWL
    -> authenticated Odoo RPC
Odoo 18 + odoo_ai_assistant
    +-- Odoo PostgreSQL
    +-- native ir.cron turn/Knowledge/import workers
    +-- provider-owned CODEX_HOME
    +-- ephemeral Codex App Server subprocess
    +-- private Assistant runtime/cache/source workspace tree
    +-- optional P10 AF_UNIX host broker when finite host privilege is required
```

There is no product-required Assistant HTTP sidecar or second Assistant database.

## Host authority

The model proposes. Host/Odoo code owns:

```text
identity / companies / groups
ACL / record rules / field access
capability identity/schema/availability
Skills / Context / Evidence composition
budgets
policy / autonomy / approval
EffectPlan / preconditions / write barrier
execution / verification / receipts / recovery
scheduler/backpressure
public activity/final projection
P12 source/workspace path resolution and fingerprints
```

Normal business operations use the effective Odoo Environment with `su=False`.
Technical reach and autonomy are independent. Model text, source/docs/logs or file
contents cannot grant authority.

## Durable provider-neutral agent runtime

A browser request persists a turn before long provider work. Odoo owns queue/lease,
cancellation, stale recovery, causal ordering, settings snapshots, TaskPlan, typed
EffectPlan, EffectJournal, interventions and reconnectable public progress.

The provider-neutral decision loop can answer, update the public TaskPlan, call a
reasoning capability or propose a typed effect step. Provider output is always
validated input.

## Capability and extension architecture

`CapabilityDefinition` remains the only atomic executable contract.

```text
CapabilityProvider
  +-- CapabilityDefinition(s)
  +-- SkillDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
```

The same registry/executor/policy path is intended for chat and future invocation
surfaces. No parallel tool authority list exists.

There is no arbitrary SQL, Python, shell, sudo or unrestricted ORM-method capability.

## Evidence and Knowledge

Evidence is bounded non-executable data with logical locator, provenance, access scope,
fingerprint/freshness and trust. Current Evidence covers runtime/module facts,
installed-addon source/XML, configured logs and company Knowledge. Search/fetch
rechecks access/freshness; retrieved prompt-injection text remains untrusted data.

Mutable business truth continues to come from live ORM authority.

## Effect lifecycle

Protected effects use:

```text
resolve typed capability
 -> validate args/eligibility
 -> preview + precondition fingerprint
 -> policy / approval when required
 -> revalidate binding
 -> durable barrier
 -> execute
 -> verify
 -> receipt / recovery
```

Ambiguous effects are never blindly retried.

## P10 privileged host boundary

ADR-024 permits an optional local AF_UNIX broker only for finite deployment-owned host
operations. It verifies peer identity and bounded request binding, maps logical target
ids to exact resources, uses fixed argv where external executables are required and
persists effect receipts/replay state. It is not a shell or another Assistant runtime.

## P11 durable data workflows

Large CSV imports are durable Odoo sessions/chunks under the originating effective
user. Staged rows, cursor and chunk receipts create explicit replay/recovery semantics.
Deterministic cleanup and rejected-window repair remain finite typed operations rather
than arbitrary transformation scripts.

## P12 controlled source modification boundary

ADR-025 adds a second important distinction:

```text
installed addon source       read-only baseline for ordinary Assistant mutation
private source workspace     mutable staging area for future typed P12 operations
production deployment        separate future effect boundary
```

P12.1 resolves an installed module host-side, snapshots bounded regular files into the
private workspace tree and records canonical content fingerprints. The model sees
logical module/workspace ids and path-free fingerprints/counts, not physical addon or
`data_dir` paths.

Workspace identity is bound to the Technical Odoo context through user/company,
hashed database identity and originating turn. Source/workspace roots must be disjoint;
symlink/path escape and binding violations fail closed.

P12.1 intentionally exposes no source-edit capability. The intended later chain is:

```text
P12.2 typed proposed diff/patch -> workspace fingerprint
P12.3 test receipt              -> exact post-patch fingerprint
P12.4 typed deploy              -> current source + approved diff + PASS test receipt
                                  -> verify + recovery classification
```

A future protected deployment extends ADR-024 or an equivalently narrow deployment
adapter. It does not turn the Odoo process into a general Git/filesystem administrator.
If the production source changed after staging, deployment is stale and must be
reprepared/rebased rather than overwriting newer code.

## Public activity and observability

Public progress is sanitized host-observed state, not private reasoning. ADR-023 limits
default telemetry to ids/timing/outcome/counts/bytes/health rather than raw prompts,
source excerpts, secrets or private reasoning.

## Persistence and filesystem

Operational product state remains Odoo-native where it has business/recovery value.
Provider credentials/caches and P12 staging files use bounded host-owned runtime paths.
The P10 broker persists only its small privileged request ledger/backups.

P12 workspaces live conceptually at:

```text
<odoo data_dir>/odoo_ai_assistant/source/workspaces/
```

They are private staging state, never automatically added to Odoo's `addons_path` and
never proof that a production deploy is authorized.

## Validation

Validation is incremental:

```text
changed contract -> focused dependency-light/static -> directly affected Odoo/host
 -> named real gates -> broad periodic regression only when explicitly required
```

P0-P11 are accepted. P12.1 implementation is present but its focused Odoo/path
authority gate is pending. See `research/P12_FOCUSED_VALIDATION_RUNBOOK.md`.
