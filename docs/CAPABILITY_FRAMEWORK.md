# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning
and deterministic Odoo/host execution. `PRODUCT_VISION.md` defines the target product;
`CURRENT_STATE.md` and current code define what exists now.

## 1. Core rule

Declare an executable operation once as a `CapabilityDefinition`, then derive the
views needed by reasoning, planning, diagnostics, Settings and future invocation
surfaces from that trusted definition.

Do not create parallel tool/action registries for chat, MCP, automations or AI fields.
The model proposes; the host validates and executes.

## 2. Atomic executable definition

`CapabilityDefinition` remains the only atomic executable unit. It carries:

```text
stable name + version
title / semantic description
input + output JSON Schema
risk + effect classification
exposure: reasoning | plan | host
approval semantics
groups / guards / dependencies / configuration
record / byte / time / call budgets
trusted handler
optional preview / verification
safe public activity metadata
```

Definitions and surrounding capability/context/Skill/provider JSON contracts are
deeply normalized and immutable after registration. Group/guard exceptions fail
closed.

There is no generic arbitrary SQL, Python, shell, sudo or unrestricted ORM-method
execution surface.

## 3. Provider extension boundary

Trusted installed Odoo addons may contribute a versioned `CapabilityProvider`
discovered from the active registry.

```text
CapabilityProvider
  +-- CapabilityDefinition(s)
  +-- SkillDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
  +-- immutable provider metadata
```

Core namespaces such as `odoo.*`, `assistant.*` and `host.*` are reserved unless the
provider is core-owned.

API mismatch, loader failure, identity/capability collisions, dependency/version
errors and dependency cycles are provider-boundary failures. Optional failures are
isolated; required providers fail closed. Sanitized introspection never exposes raw
exceptions, secrets or arbitrary host paths.

## 4. Effective registry and executor

```text
core definitions
 + trusted installed CapabilityProvider(s)
 -> deterministic CapabilityRegistry
 -> user/context/configuration filtering
 -> CapabilityExecutor
```

`CapabilityRegistry` owns effective identity and availability. A hidden, disabled,
missing-config or unauthorized operation does not become executable because the user
or model knows its name.

`CapabilityExecutor` performs:

```text
resolve
 -> validate input
 -> resolve configuration
 -> check effective availability
 -> policy / authority
 -> execute trusted handler
 -> validate bounded output
 -> emit safe host-known activity
```

Normal business handlers use the effective Odoo user with `su=False`.

## 5. Reads and effects

READ/analysis calls may iterate under exploration, cost, latency and output budgets
and current Odoo ACLs.

Effects remain host controlled:

```text
model proposes typed step
 -> host resolves CapabilityDefinition
 -> validate args + eligibility
 -> preview / preconditions
 -> policy
 -> approval when required
 -> durable write barrier
 -> execute
 -> verify
 -> receipt / recovery
```

Approval is policy/autonomy-driven. Full-control can avoid a redundant confirmation
only for an operation already available to the effective user and explicitly allowed
by trusted policy. Autonomy never expands ACLs, record rules, field access, companies,
Technical profile or broker policy.

Ambiguous effects are not retried blindly.

## 6. Skills / Bundles

`SkillDefinition` groups semantic behavior above atomic executable capabilities. It
may contain:

```text
description / title / version
trusted instructions / examples
capability selectors
ContextProvider selectors
EvidenceProvider selectors
activation / configuration metadata
eval ownership
```

Skills never execute and never own ACL, policy or approval. The product exposes one
global Assistant; Skills are not separate authority-owning bots.

## 7. ContextProvider

A `ContextProvider` supplies bounded just-in-time contextual data. Its output is deeply
frozen untrusted data and cannot:

- register or reveal hidden capabilities;
- change policy;
- grant groups or permissions;
- approve effects;
- become trusted instructions.

Context is resolved progressively instead of dumping the whole installation into
every model call.

## 8. EvidenceProvider

Evidence is a first-class non-executable resource on the same extension boundary.

```text
EvidenceKind / Trust / Freshness
EvidenceAccessScope / Locator
EvidenceRef / EvidenceItem
EvidenceSearchRequest / EvidenceSearchResult
EvidenceProvider / EvidenceProviderStatus
EvidenceProviderCatalog
EvidenceRoutingPolicy
EvidenceLedger / EvidenceLedgerSnapshot
AssistantEvidenceDecisionEngine / EvidenceWorkingContext
```

Search returns bounded refs. Fetch resolves a logical locator and rechecks provider
identity, access scope, fingerprint/freshness and output bounds.

Evidence supports conclusions but never changes capability availability, product
profile, policy, approval or broker targets.

## 9. Evidence routing and live projection

`EvidenceRoutingPolicy` prioritizes evidence classes without recreating a rigid
GENERAL/QUERY/HOW_TO/ACTION router. It may select no provider for a generic/social
turn.

Current direction:

```text
business/current state      -> live ORM before snapshots/docs
installation behavior       -> runtime/schema/source/XML/config
standard HOW_TO              -> official/versioned docs + local verification
error diagnosis              -> turn trace + logs + source/XML/runtime
company policy               -> Knowledge/document providers
module/repository HOW_TO     -> README/docs/manifest/source/install state
current external fact        -> web when policy/context allows
repository preflight         -> web/repo metadata + bounded static inspection
```

Retrieved content remains in the untrusted-data partition.

## 10. EffectiveAssistantManifest

`EffectiveAssistantManifest` is a sanitized projection, not an authority registry. It
includes provider/features, public profile, active Skills, model-visible capabilities,
ContextProvider IDs, EvidenceProvider IDs and configuration health.

Retrieved Evidence, secrets and host-only broker details do not belong in the
manifest.

## 11. Product profiles

Product-facing profile values are exactly:

```text
user
technical
```

Older internal `business`/`developer` names remain compatibility details only.
Profile projection itself grants no permission.

The P10 broker is a machine execution boundary, not a third human profile.

## 12. Progressive disclosure

The framework models:

```text
discovered -> available -> revealed -> active
```

Ordinary schemas may remain eager. Lazy/on-demand disclosure is promoted only when
evals show equal-or-better task/tool-selection quality and useful context/latency/cost
improvement.

Pydantic AI/FastMCP-style patterns remain references, not runtime dependencies.

## 13. Invocation surfaces

Chat is one consumer. Future MCP, automations, AI fields, context launchers and other
surfaces reuse:

```text
CapabilityDefinition
CapabilityRegistry / CapabilityExecutor
Skill / Context / Evidence contracts
policy / ACL / profile / budgets
turn / effect / audit infrastructure where applicable
```

A new surface may have a different effective projection, but not a divergent authority
list.

## 14. Host-risk capabilities

`CapabilityRisk.HOST` and `CapabilityEffect.HOST` describe operations whose effect is
outside ordinary Odoo business transaction authority. They map to the protected risk
band and must be PLAN capabilities with preview and verification.

The implemented P10 split is:

```text
Odoo-local Technical reads
  odoo.module.inspect
  postgres.health

broker-backed Technical reads/effects
  odoo.config.inspect
  odoo.config.patch
  host.service.status
  host.service.restart
```

All require `base.group_system`. Broker-backed definitions are additionally guarded by
broker availability and final broker peer/policy checks.

Effectful broker definitions declare external recovery. They still use the same
EffectPlan, policy, write barrier, verification and recovery infrastructure; the
broker is an adapter behind the definition, not another registry.

## 15. Broker request authority

The optional Linux broker accepts only a versioned finite operation protocol over a
local Unix socket. The Odoo client binds an execute request to:

```text
turn id
conversation id
effective Odoo uid
hashed database identity
capability / operation
EffectPlan step id
canonical args hash
plan binding fingerprint
preview precondition fingerprint
```

The deployment-owned broker policy maps logical target ids to exact config paths or
systemd units. Model text never supplies an executable or filesystem path.

The broker independently validates peer UID, request lifetime, operation/phase, shape,
target, args hash and precondition.

## 16. Host receipts, replay and uncertainty

Before a privileged effect, the broker ledger stores the canonical request as
`running`.

```text
same id + same hash + terminal receipt -> return receipt, no re-execution
same id + changed hash                 -> deny
same id still running                  -> uncertain, no re-execution
```

The receipt returns bounded status, effect state, pre/post fingerprints, sanitized
summary and recovery classification. Raw stdout/stderr, config secrets and environment
variables are not product results.

Transport, framing, decoding or receipt-validation failure after an effectful request
starts dispatching is `host_effect_uncertain`. It is never projected as ordinary
broker unavailability or proof that no effect occurred.

Read-only broker calls retain normal unavailable/invalid-response behavior.

## 17. Concrete first-slice host semantics

### Config inspect/patch

- input contains logical target and allowlisted non-secret key;
- policy resolves the path;
- preview returns current/new value and file fingerprint;
- execute requires the exact fingerprint;
- replacement is same-filesystem, fsynced and atomic;
- a private backup is stored before a change;
- verify re-reads the key and postcondition fingerprint.

### Service status/restart

- input contains one logical target;
- policy resolves one exact `.service` unit;
- fixed argv is run with `shell=False`;
- status parses only bounded known fields;
- restart requires preview fingerprint;
- post-restart health is verified;
- timeout/failure after the restart barrier is external/unknown.

### PostgreSQL health

- executes fixed host-owned read SQL only;
- accepts no SQL/query input;
- returns bounded current database counts/version/size.

### Module inspect

- reads one current Odoo module and bounded metadata;
- performs no install/update/uninstall method.

## 18. Unsupported host breadth

Not implemented:

```text
odoo.module.install/update/uninstall
repository acquire/promote
host package install
config rollback capability
secret reveal
generic command fallback
```

Odoo 18 immediate module maintenance cannot safely run inside the current Assistant
cron worker. A separate lifecycle-safe maintenance adapter must persist an
exactly-once receipt and verify a fresh registry before
`P10-REAL-MODULE-UPDATE` can pass.

A generic command fallback remains forbidden unless a separate ADR and its conditional
real gates are accepted.

## 19. Security checklist

Every executable capability must answer:

1. What exact operation is allowed?
2. What schemas and byte/record/time/call limits bind it?
3. What effective user/company/groups/profile apply?
4. Is returned content host fact or untrusted Evidence/data?
5. What risk/effect class applies?
6. What preview/approval policy applies at each autonomy level?
7. How is success verified?
8. What happens on timeout, cancellation or restart?
9. Can a replay duplicate an effect?
10. What state is reported if the effect may have occurred?

For broker-backed operations additionally answer:

11. What logical target does policy map to what exact resource?
12. How are caller and broker peer identities verified?
13. What request/precondition binding reaches the broker?
14. What is persisted before the privileged barrier?
15. What bounded receipt and recovery class are returned?
16. Can loss after dispatch ever be mistaken for a safe retry? The answer must be no.

## 20. Validation state

P0-P9 contracts are accepted on their recorded lineages. P10's first implementation
and test surfaces exist, but focused and real gates remain unexecuted.
`P10-REAL-MODULE-UPDATE` is blocked by the missing maintenance adapter.

See:

```text
docs/adr/ADR-024-technical-host-privilege-broker.md
docs/research/P10_HOST_OPERATIONS_FIRST_SLICE.md
docs/research/P10_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/EXECUTION_STATE.md
host_broker/README.md
```
