# Architecture

Current architecture for `CPX-001/ai-odoo-assistant`. Code plus accepted ADRs are
authoritative. `CURRENT_STATE.md` summarizes the implementation and
`research/EXECUTION_STATE.md` owns the roadmap cursor/validation debt.

## 1. Deployment unit

The supported product is an Odoo 18 Community addon with an embedded agent runtime.

```text
Browser / OWL
    |
    | authenticated Odoo RPC
    v
Odoo 18 + odoo_ai_assistant
    |
    +-- Odoo PostgreSQL
    +-- native ir.cron turn workers
    +-- provider-owned CODEX_HOME
    +-- Codex App Server subprocess
```

The supported product requires no FastAPI/Uvicorn Assistant sidecar, second Assistant
database, internal sidecar HTTP port or shared machine secret. The obsolete
`auth="none"` inventory callback, addon-local machine-auth primitive and residual
addon inventory service are removed.

Future host-level privilege may require a narrow local broker. ADR-024 is proposed
only; that broker must not become a general sidecar or passwordless-root Odoo process.

## 2. Authority boundary

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

The model proposes. It cannot grant permissions, approve itself, reveal hidden tools
or turn Evidence into authority.

Normal business operations use the effective Odoo `Environment` with `su=False`.
Narrow host facts such as the installed-module set may use Odoo-owned internal host
metadata helpers; that does not create a generic sudo/business-record path and the
resulting Evidence is still bound to the requesting user/company scope.

## 3. Durable turn runtime

A submitted message is persisted before long-running provider work. The current
accepted P5/P6 path provides:

- queued/running/approval/terminal states;
- lease/attempt/cancellation/stale recovery;
- native cron claim workers and bounded concurrency;
- one active causal turn per conversation;
- cross-conversation parallelism/fairness;
- immutable per-turn model/reasoning/autonomy/planning settings;
- persisted public/live events and reconnectable status.

A browser connection does not own the server turn.

## 4. Provider-neutral agent loop

`AgentTurnService` and the provider-neutral decision layer operate conceptually as:

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
Structured Outputs translation, provider events/errors, streaming deltas and
steer/interrupt mechanics.

## 5. Capability architecture

`CapabilityDefinition` is the atomic executable contract.

```text
CapabilityProvider
  -> Skill / Bundle
      -> CapabilityDefinition selectors
      -> ContextProvider selectors
      -> EvidenceProvider selectors
```

The current provider API is versioned (`CAPABILITY_PROVIDER_API_VERSION = "1"`).
Core provider/resource namespaces are reserved. API mismatch, loader/collision,
dependency/cycle, guard and Evidence failures are isolated to attributable optional
providers; required authority fails closed.

The same registry/executor is the intended authority source for future chat,
automation, AI-field and MCP projections. No parallel tool registry is introduced.

There is no arbitrary SQL, Python, shell, sudo or unrestricted ORM-method surface.

## 6. Context architecture

Turns start with a small bounded base derived from host state:

```text
user/company/lang/tz
screen/record/view hints
conversation state
effective Assistant manifest
immutable turn settings
```

`ContextProvider`s add just-in-time contextual data selected by active Skills. Their
content is deeply immutable untrusted data and cannot change permissions/policy/tool
authority.

Global installation knowledge is not dumped into every prompt.

## 7. Evidence architecture

P8 introduces a shared non-executable Evidence layer:

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

`EvidenceProviderCatalog` handles availability/search/fetch isolation and
`EvidenceRoutingPolicy` prioritizes source classes according to the question without
becoming a rigid intent router. Generic/social turns can select no provider.

Evidence is always data. Search/fetch access is checked against the current context;
fetch revalidates access and freshness. Retrieved prompt-injection text remains in the
untrusted-data partition.

The first real provider, `assistant.runtime_inventory`, exposes bounded current
installation facts (release, sanitized DB identity, installed modules, registry
fingerprint). The installed module set comes from Odoo's own narrow host metadata
primitive so normal users do not need `ir.module.module` read ACL. It exposes no
business records, addon roots or credentials. Mutable business truth remains live ORM
authority.

The first live retrieval seam is implemented:

```text
AssistantExtensionDecisionEngine
 -> effective Evidence providers
 -> question-sensitive routing
 -> bounded search/fetch
 -> bounded turn EvidenceLedger
 -> host structural metadata + untrusted Evidence data
 -> reasoning provider
```

The current live ledger is turn-scoped. Durable reconnect restoration and richer
end-user citation rendering are not claimed yet.

See `EVIDENCE_ARCHITECTURE.md`.

## 8. Source scope

P8 source intelligence must prefer the current installation and avoid accidental
contamination from retired implementation lineages.

Default current sources include the active addon, installed/trusted addons, Odoo 18
core/addons and current tests when behavior evidence is requested. Historical
`service/`, `installer/`, root migrations, old task packets and evidence archives are
excluded from normal current context by policy, not deleted.

See `CONTEXT_SOURCE_POLICY.md` and
`addons/odoo_ai_assistant/runtime/context_source_policy.json`.

## 9. Effective Assistant manifest

`EffectiveAssistantManifest` is a host-derived self-description, not an authority
registry. It projects sanitized effective state such as:

```text
provider profile/features
public product profile
active Skills
model-visible capabilities
ContextProvider IDs
EvidenceProvider IDs
configuration/availability summaries
```

Retrieved Evidence content, secrets and host-only details do not belong in the
manifest. Settings/admin projection derives the same effective available Evidence
provider IDs rather than maintaining a separate list.

## 10. Product profiles and autonomy

Product-facing profile values are exactly:

```text
user
technical
```

Internal historical `business`/`developer` names may map to these two values for
compatibility. The future Technical/host broker is an execution boundary, not another
human profile.

Autonomy is independent of technical reach. Full-control can suppress redundant
confirmation only when trusted policy allows an effect the effective user is already
permitted to perform. It cannot expand Odoo authority.

## 11. Effect lifecycle and recovery

Current bounded effects use:

```text
typed proposals
 -> prepare/preview + preconditions
 -> policy / approval when required
 -> revalidate binding/preconditions
 -> recovery-unit checkpoint / write barrier
 -> execute as effective user
 -> verify
 -> receipt / EffectJournal / recovery state
```

Recovery semantics distinguish Odoo-atomic, segmented and external/uncertain units.
Persisted in-flight effects are never blindly replayed and ambiguous writes are not
auto-retried.

## 12. Public activity and streaming

Public progress is a sanitized projection of host-observed work, not model private
reasoning. Persisted activity, TaskPlan/reasoning summary and answer streaming are
separate data surfaces.

The browser currently consumes authenticated Odoo polling/live cursors. Polling vs
bus/SSE remains an optimization; durable Odoo state is authoritative.

Raw prompts, private reasoning, sensitive tool arguments/results and credentials must
not be emitted as public progress.

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

Default telemetry is metadata/timing/outcome/counts/bytes, not full sensitive
content. Detailed diagnostic content requires explicit authorization, redaction,
bounds and retention policy.

No second tracing database or mandatory sidecar is introduced.

## 14. Secret handling

Secret-looking values in Evidence/metadata are redacted by bounded normalization.
A secret pasted by the user is data, not authority, and should not automatically
block otherwise safe work. Derived traces/Evidence/progress should avoid reproducing
it and the user should be warned without unnecessary re-emission.

Assistant-presented secrets require a dedicated masked/copy/reveal UI before that
behavior can be claimed complete.

## 15. Module/domain architecture

The current core manifest still depends on `sale` and `account`. P7 makes future
Odoo-native domain/link addons possible:

```text
odoo_ai_assistant
odoo_ai_assistant_sale
odoo_ai_assistant_account
...
```

This split is not performed merely for aesthetics. It must preserve one customer
product/install experience and be proven with clean install/update/uninstall tests.
Odoo's `auto_install` link-module pattern is the preferred reference where correct.

## 16. Future repository/host operations

The direction is **discovery + bounded Evidence + typed promotion**, not shell or ORM
escape hatches.

A future `ModuleAcquisitionSession` can resolve arbitrary candidate repositories,
perform bounded web/repo/manifest/license/dependency/static preflight, assess
compatibility/risk, then select a policy-driven direct or staged path. Allowlists may
be trust signals/customer policy but are not universal product requirements.

Operations that truly cross the OS/service/filesystem privilege boundary belong
behind the minimal ADR-024 broker with fixed schemas, managed roots/targets,
request binding, time/output bounds, receipts and recovery.

## 17. Persistence

Operational state stays Odoo-native:

- conversations/messages/turns;
- queue/lease/recovery;
- working items and public events;
- effect plans/receipts/EffectJournal;
- configuration;
- bounded Evidence ledger/state when continuation requires durability.

No P8 design restores the retired Assistant SQLAlchemy database.

## 18. Validation architecture

Validation is incremental and evidence-based:

```text
changed contract
 -> focused unit/contract tests
 -> directly affected Odoo/browser boundary
 -> named real gates when required
 -> periodic full regression only when the runbook/user requires it
```

P7 and P8 are accepted. P8's provider-neutral Evidence projection, runtime inventory,
installed-addon source/XML provider, configured-log provider and browser-safe
citations passed 61 focused dependency-light tests, 20 focused Odoo tests and all six
real Evidence gates. Broad regression suites remain explicit periodic debt.

See `research/P8_FOCUSED_VALIDATION_RUNBOOK.md` and
`research/EXECUTION_STATE.md`.
