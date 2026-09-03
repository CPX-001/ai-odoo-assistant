# Architecture

Current architecture for `CPX-001/ai-odoo-assistant`. Code plus accepted ADRs are
authoritative. `CURRENT_STATE.md` summarizes implementation and
`research/EXECUTION_STATE.md` owns the roadmap cursor and validation debt.

## 1. Deployment units

The supported product is an Odoo 18 Community addon with an embedded agent runtime:

```text
Browser / OWL
    |
    | authenticated Odoo RPC
    v
Odoo 18 + odoo_ai_assistant
    |
    +-- Odoo PostgreSQL
    +-- native ir.cron turn/Knowledge workers
    +-- provider-owned CODEX_HOME
    +-- ephemeral Codex App Server subprocess
```

The supported product requires no Assistant HTTP sidecar, second Assistant database,
internal sidecar port or shared machine secret.

Phase 10 adds an optional local machine adapter only when deployment-owned host
privilege is required:

```text
Odoo EffectPlan
    |
    | bounded canonical request over AF_UNIX
    v
odoo-ai-host-broker
    |
    +-- deployment policy
    +-- durable request/receipt ledger
    +-- exact managed config/service target
```

The broker is not the Assistant runtime. It does not run the model, own conversation
state or replace the Odoo queue. ADR-024 forbids turning it into a general sidecar,
shell or passwordless-root Odoo process.

## 2. Authority boundaries

Odoo/host code owns:

```text
identity + companies
ACL / record rules / field access
schema/capability visibility
conversation/turn durability
CapabilityProvider composition
Skills / Context / Evidence availability
budgets
policy/autonomy/approval
EffectPlan + write barrier
execution + verification + recovery
audit/public progress projections
scheduler/backpressure
```

The optional broker owns only its finite privileged target boundary:

```text
caller UID policy
broker peer identity
operation and phase allowlist
logical target -> exact path/service mapping
request lifetime/size/binding validation
host precondition checks
effect request replay ledger
sanitized receipt/recovery classification
```

The model proposes. It cannot grant permissions, approve itself, reveal hidden tools,
turn Evidence into authority, create a broker target or supply a command/path.

Normal business operations use the effective Odoo `Environment` with `su=False`.
Technical profile and autonomy are independent. Full autonomy cannot make a User
profile Technical or widen broker policy.

## 3. Durable turn runtime

A submitted message is persisted before long-running provider work. The accepted
P5/P6 path provides:

- queued/running/approval/terminal states;
- lease, attempt, cancellation and stale recovery;
- native cron claim workers and bounded concurrency;
- one active causal turn per conversation;
- cross-conversation parallelism and fairness;
- immutable per-turn model/reasoning/autonomy/planning settings;
- persisted public/live events and reconnectable status;
- a durable write barrier and recovery-unit checkpoints.

A browser connection does not own the server turn.

## 4. Provider-neutral agent loop

`AgentTurnService` and the provider-neutral decision layer operate as:

```text
provider decision
  -> final_answer
  OR task_plan_update
  OR reasoning_capability_call
  OR plan_step_proposal
```

Provider output is validated input. The host resolves effective capability identity,
schema, budgets, policy and effect state.

`TaskPlan` is public orchestration/progress. `EffectPlan` is a separate typed
host-authorized effect proposal. Neither is private chain-of-thought.

Codex-specific code stays below this boundary and owns App Server transport,
Structured Outputs translation, provider events/errors, streaming and interruption.

## 5. Capability architecture

`CapabilityDefinition` is the atomic executable contract.

```text
CapabilityProvider
  -> Skill / Bundle
      -> CapabilityDefinition selectors
      -> ContextProvider selectors
      -> EvidenceProvider selectors
```

The provider API is versioned. Core namespaces are reserved. API mismatch,
loader/collision, dependency/cycle, guard and Evidence failures are isolated to
attributable optional providers; required authority fails closed.

The same registry/executor is the intended authority source for chat, future
automation, AI-field and MCP projections. No parallel tool registry is introduced.

There is no arbitrary SQL, Python, shell, sudo or unrestricted ORM-method surface.

## 6. Context architecture

Turns start with a small bounded base:

```text
user/company/lang/tz
screen/record/view hints
conversation state
effective Assistant manifest
immutable turn settings
```

`ContextProvider`s add just-in-time data selected by active Skills. Their content is
deeply immutable untrusted contextual data and cannot change permissions, policy or
tool authority.

Global installation knowledge is not dumped into every prompt.

## 7. Evidence and Knowledge architecture

Evidence is non-executable:

```text
EvidenceProvider
  -> EvidenceRef
      locator + provenance + access scope
      fingerprint/freshness + trust
  -> EvidenceItem
      bounded excerpt/data
  -> EvidenceLedger
      bounded selected refs/items for continuation/citations
```

Search/fetch rechecks access and freshness. Retrieved prompt-injection text stays in
the untrusted-data partition.

Current providers cover runtime inventory, installed-addon source/XML, configured
Odoo logs and company Knowledge. Live Odoo ORM remains authority for mutable business
truth. Company/private source rules are enforced before lexical retrieval.

The live decision seam is:

```text
AssistantExtensionDecisionEngine
 -> effective Evidence providers
 -> question-sensitive routing
 -> bounded search/fetch
 -> bounded turn EvidenceLedger
 -> host structural metadata + untrusted Evidence data
 -> reasoning provider
```

Generic/social turns may retrieve nothing.

## 8. Effective Assistant manifest

`EffectiveAssistantManifest` is a host-derived self-description, not an authority
registry. It projects:

```text
provider profile/features
public product profile
active Skills
model-visible capabilities
ContextProvider IDs
EvidenceProvider IDs
configuration/availability summaries
```

Retrieved content, secrets and host-only broker details do not belong in the manifest.

## 9. Product profiles and autonomy

Product-facing profile values are exactly:

```text
user
technical
```

Historical internal `business`/`developer` names may map to these values. The broker
is a machine execution boundary, not a third user profile.

Autonomy is independent of technical reach. It may suppress a redundant confirmation
only when trusted policy allows an operation already available to the effective user.
It cannot expand ACLs or broker targets.

## 10. Effect lifecycle and recovery

Effects use:

```text
typed proposals
 -> preview + preconditions
 -> policy / approval when required
 -> revalidate binding/preconditions
 -> recovery-unit checkpoint / write barrier
 -> execute
 -> verify
 -> receipt / EffectJournal / recovery state
```

Recovery distinguishes Odoo-atomic, segmented and external/uncertain units. Persisted
in-flight effects are never blindly replayed.

For broker-backed effects, the request additionally binds:

```text
turn + conversation + Odoo uid
hashed database identity
capability + plan step
canonical args
plan binding fingerprint
preview precondition fingerprint
```

The broker stores an effect request as `running` before its host barrier. Exact
terminal replay returns the stored receipt; changed replay is denied; an unresolved
running request is uncertain.

Transport/framing/receipt loss after effect dispatch is `host_effect_uncertain`, not a
safe-to-retry broker outage.

## 11. P10 Technical/host architecture

The implemented first slice separates operations that need no privilege:

```text
odoo.module.inspect
postgres.health
```

from operations that cross the machine boundary:

```text
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

All are Technical-only. Broker-backed capabilities also require a live configured
socket and final peer/policy validation.

The Linux reference adapter provides:

- AF_UNIX one-request/one-receipt framing;
- bidirectional `SO_PEERCRED`;
- secure policy and executable owner/mode checks;
- logical config/service/module targets;
- fixed-argv `systemctl`, `shell=False`;
- fixed-argv transient `systemd-run` module maintenance under a policy-owned
  non-root UID/GID;
- bounded parsed output;
- atomic config replace, fsync and private backup;
- durable SQLite replay ledger;
- explicit `none | applied | unknown` effect state.

Effectful module install/uninstall is not implemented. Update is intentionally not an
immediate ORM action: the broker launches a separate bounded Odoo CLI process and
uses another fresh registry to verify the installed/source version before success.

Repository/package promotion and a generic command fallback are also absent.

## 12. Public activity and streaming

Public progress is a sanitized projection of host-observed work, not model private
reasoning. Persisted activity, TaskPlan/reasoning summary and answer streaming are
separate surfaces.

Raw prompts, private reasoning, sensitive arguments/results, broker policy, config
secrets and credentials must not be emitted as public progress.

## 13. Observability

ADR-023 defines host-owned observability around:

```text
turn
provider decision/generation
capability call
Evidence search/fetch
effect preview / approval wait / execute / verify
public-delivery checkpoint
```

Default telemetry is metadata/timing/outcome/counts/bytes, not full sensitive content.
The P10 broker adds sanitized request/receipt identity and outcome boundaries; it does
not become a second tracing warehouse.

## 14. Secret handling

Secret-looking values in Evidence/metadata are redacted. A secret pasted by the user
is data, not authority.

The first P10 config adapter denies secret-like option names even if accidentally
allowlisted. Assistant-presented secrets require a dedicated masked/copy/reveal UI
before that behavior can be claimed.

## 15. Module/domain architecture

The core manifest still depends on `sale` and `account`. P7 permits future Odoo-native
link/domain addons:

```text
odoo_ai_assistant
odoo_ai_assistant_sale
odoo_ai_assistant_account
...
```

A split must preserve one customer install experience and pass clean
install/update/uninstall tests. It is not performed for aesthetics.

## 16. Repository and maintenance direction

The direction is discovery + bounded Evidence + typed promotion, not shell or ORM
escape hatches.

A future `ModuleAcquisitionSession` may resolve arbitrary candidate repositories,
perform bounded manifest/license/dependency/static preflight and choose a policy-
driven direct or staged path.

Any operation crossing service/filesystem privilege uses ADR-024-style fixed schemas,
managed targets, request binding, time/output bounds, receipts and recovery.

Odoo module update uses a worker-independent systemd maintenance adapter with a fresh
registry check. Repository acquisition, install/uninstall and arbitrary maintenance
commands remain absent.

## 17. Persistence

Operational state remains Odoo-native:

- conversations/messages/turns;
- queue/lease/recovery;
- working items and public events;
- effect plans/receipts/EffectJournal;
- configuration;
- bounded Evidence state when continuation requires durability.

The broker persists only its small privileged request/receipt ledger and private
operation backups. It does not restore the retired Assistant SQLAlchemy database.

## 18. Validation architecture

Validation is incremental:

```text
changed contract
 -> focused unit/contract tests
 -> directly affected Odoo/broker boundary
 -> named real gates
 -> periodic full regression only when required
```

P0-P10 are accepted. P10's typed operations and module-maintenance adapter passed the
focused and named real gates. See `research/P10_FOCUSED_VALIDATION_RUNBOOK.md` and
`research/EXECUTION_STATE.md`.
