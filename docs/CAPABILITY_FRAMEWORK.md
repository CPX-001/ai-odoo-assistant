# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning and deterministic Odoo/host
execution. `PRODUCT_VISION.md` defines the target product; this document defines the current capability boundary.

## 1. Core principle

Declare an executable operation once as a `CapabilityDefinition`, then derive reasoning, planning, diagnostics,
Settings and future invocation-surface views from the same trusted definition.

Do not create separate registries for chat tools, MCP, automations or AI fields when they represent the same operation.
The model may reason broadly, but **authority remains explicit and host-owned**.

## 2. Atomic executable definition

`CapabilityDefinition` is the only Phase-7 unit that can represent an executable operation. It includes:

```text
stable name + version
title / description
input + output JSON Schema
risk + effect classification
exposure: reasoning | plan | host
approval semantics
groups / guards / dependencies / configuration
record/byte/time/call budgets
trusted handler
optional preview / verification
safe public activity metadata
```

Handlers are registered only by trusted installed code or a separately designed declarative mechanism. Model-generated
text never becomes executable code merely because it names a function, ORM method, SQL statement or shell command.

## 3. Current provider composition

Current core capability modules remain under:

```text
runtime/capabilities/providers/
```

Trusted installed Odoo addons may additionally contribute a `CapabilityProvider` marker through the active Odoo
registry. Effective composition is:

```text
cached core registry
 + trusted installed CapabilityProvider(s)
 -> deterministic CapabilityRegistry
 -> effective user/context filtering
 -> CapabilityExecutor
```

Provider identity/capability/executor collisions fail closed. An optional provider failure is sanitized and isolated;
it cannot shadow or remove the core catalog.

The live Odoo-owned host loop, capability Settings/diagnostics and reversion/compensation paths use
`discover_capabilities_for_env(env)`.

## 4. Effective registry and authority

`CapabilityRegistry` is the authority for effective identity and availability. It evaluates host-known state such as:

```text
installed provider/module
enablement
user/groups/companies
guards/dependencies
current run context
invocation exposure
```

Declarative configuration readiness is resolved by `CapabilityConfigResolver`; runtime availability may suppress a
definition the host already knows cannot satisfy its required configuration while keeping it visible to Settings for
diagnosis.

A hidden, disabled, missing-config or unauthorized operation does not become executable because the user/model knows
its name.

## 5. Executor

`CapabilityExecutor` performs the shared lifecycle:

```text
resolve
 -> validate input
 -> resolve configuration
 -> check effective availability
 -> policy/authority
 -> execute trusted handler
 -> validate bounded output
 -> emit safe host-known activity
```

Business handlers use the effective Odoo user and `su=False`. `sudo()` is not a convenience shortcut for model-visible
business authority.

## 6. Reads and effects

READ/analysis operations may be iterative but remain bounded by exploration/call/latency/output budgets and Odoo ACLs.

Effects remain host controlled:

```text
model proposes typed step
 -> host resolves definition
 -> validate arguments
 -> preview/preconditions
 -> policy/approval
 -> durable write barrier
 -> execute
 -> verify
 -> receipt/recovery state
```

Multi-step EffectPlans are compositions of typed `CapabilityDefinition` steps, not provider-authored programs.

## 7. CapabilityProvider

`CapabilityProvider` is the trusted installed-addon extension boundary. A provider may contribute:

```text
CapabilityDefinition(s)
SkillDefinition(s)
ContextProvider(s)
provider metadata
```

Future EvidenceProvider resources may join the same provider layer without changing executable authority.

Provider discovery uses the active Odoo registry marker `_odoo_ai_capability_provider`; it does not scan arbitrary host
packages/filesystem paths.

## 8. Skill / Bundle

`SkillDefinition` groups semantic behavior above atomic capabilities. It may contain:

```text
description/title/version
trusted instructions/examples
capability selectors
ContextProvider selectors
future EvidenceProvider selectors
activation/configuration metadata
eval ownership
```

Skills **never execute** and never own ACL/policy/approval. Active Skill instructions are trusted installed-code
behavior guidance only. Every actual operation still resolves through the effective capability registry/executor.

There remains one global user-facing Assistant; Skills are not a forced collection of separate bots.

## 9. ContextProvider

A `ContextProvider` supplies bounded just-in-time contextual data such as current module/view/domain state.

The Phase-7 live path activates only providers selected by active Skills. Their output is validated/bounded and passed
to the reasoning provider as **untrusted contextual data**. Retrieved/contextual text cannot:

- register capabilities;
- change policy;
- grant a group/permission;
- approve an effect;
- convert itself into trusted instructions.

## 10. ProviderProfile

`ProviderProfile` describes what the configured reasoning integration actually exposes through this addon:

```text
structured_output
tool_calling
answer_streaming
vision
file_input
web
large_context
```

Each feature is explicit:

```text
native | emulated | unavailable
```

Capacity metadata is recorded only when host-known/measured; it is not guessed from provider marketing.

The current Codex App Server profile is intentionally conservative. This metadata affects feature negotiation and
self-awareness, not Odoo execution authority.

## 11. EffectiveAssistantManifest

`EffectiveAssistantManifest` is derived from current effective host state:

```text
provider profile/features
technical access profile
active Skills
model-visible REASONING/PLAN capabilities
ContextProviders
provider/configuration health
known unavailable features
disclosure state
```

Host-only capabilities are excluded from the model/user self-description projection.

The manifest powers natural questions such as `¿qué puedes hacer?` and is also available through admin diagnostics. It
is a projection of the real authority/configuration graph, never a second registry that grants authority.

## 12. Technical access profile

Phase 7 defines descriptive technical profiles:

```text
Business/User
Developer/Operator
```

They separate how much technical reach may eventually be exposed from how autonomously an operation may run. Phase 7
does **not** grant privileged host operations. Filesystem/service/Postgres/source-write capabilities remain later work
behind explicit privilege boundaries and ADRs.

## 13. Progressive disclosure

The framework models:

```text
discovered -> available -> revealed -> active
```

The current product remains eager by default. A large catalog is not enough reason to hide schemas blindly.
Progressive/lazy disclosure may be promoted only when the permanent eval suite and `P7-REAL-DISCLOSURE` show
acceptable/equal-or-better task and tool-selection quality plus useful latency/token characteristics.

Skills/namespaces provide the semantic grouping needed for that future promotion. OpenAI Agents tool-search/namespaces
are a useful reference for deferred long-tail schemas, but the addon does not introduce the Agents SDK as a second
runtime dependency.

## 14. Generic Odoo providers

Current generic providers remain semantic/bounded rather than arbitrary escape hatches:

- query/schema capabilities for live Odoo data;
- explicit typed actions;
- bounded batch operations;
- bounded related-record workflows;
- runtime/navigation helpers;
- compensation helpers.

`odoo.workflow.batch_create_graph` is the first generic workflow capability. It accepts two to five ordered create
steps and lets a later many2one value reference a record created by an earlier step. The entire graph is still one
`CapabilityDefinition`: Odoo validates every model, field, relation, ACL and reference, executes it in the current
transaction as the effective user, and verifies every created record. This reduces model round trips for dependent
work such as “create contacts, then use those exact contacts in quotations” without adding a second action registry
or model-authored executable program.

Independent rows should continue to use the ordinary batch capability. A workflow is appropriate when a dependency
edge exists; it is not a reason to wrap every CRUD call in orchestration.

There is no generic arbitrary SQL, Python, shell, sudo or unrestricted ORM-method execution surface.

## 15. Future technical/host capabilities

The framework is not permanently limited to CRUD. Future explicit capabilities may encapsulate source/log/module,
configuration, service or network operations if they define:

```text
authority profile
input/output schema
path/target allowlists where relevant
preview/preconditions
policy/approval
verification
recovery/audit
budgets
```

Prefer high-level semantic capabilities over generic shell. Direct source modification belongs to a staged
patch/diff/test/deploy/verify lifecycle, not unrestricted production editing.

## 16. Invocation surfaces

Chat is one invocation surface over the same contract. Future MCP, automation, AI fields or context launchers should
reuse:

```text
CapabilityDefinition
CapabilityRegistry
CapabilityExecutor
policy/ACL/technical profile
Context/Evidence contracts
```

Each surface may receive a different effective projection, but should not maintain a divergent authority list.

Apexive's reuse of one Odoo tool framework for built-in chat and MCP and OCA's cross-surface `ai_tool` direction are
useful implementation references for this principle.

## 17. Security checklist for a new executable capability

Every new capability must answer:

1. What exact operation is allowed?
2. What schemas and byte/record/time/call limits bound it?
3. What effective user/company/groups/technical profile apply?
4. Is returned content trusted host fact or untrusted evidence/data?
5. What risk/effect class applies?
6. What preview/approval is required?
7. How is success verified?
8. What happens on timeout/cancel/restart?
9. Can it be retried/reconstructed/reverted or only reviewed?
10. What public activity is safe to expose?
11. What deterministic/product/real gates block promotion?

## 18. Phase-7 validation status

The Phase-7 implementation is present, but acceptance remains pending. The trusted fixture addon and deterministic
coverage are prepared; the consolidated Product Behavior + P7 real gates are defined in:

```text
docs/research/P7_CONSOLIDATED_VALIDATION_RUNBOOK.md
```

Do not treat implementation presence as evidence that the Phase-7 real/provider/product behavior gates pass.
