# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning
and deterministic Odoo/host execution. `PRODUCT_VISION.md` defines the target
product; `CURRENT_STATE.md` and current code define what exists now.

## 1. Core rule

Declare an executable operation once as a `CapabilityDefinition`, then derive the
views needed by reasoning, planning, diagnostics, Settings and future invocation
surfaces from that trusted definition.

Do not create parallel tool/action registries for chat, MCP, automations or AI fields.
The model can propose; the host validates and executes.

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
record/byte/time/call budgets
trusted handler
optional preview / verification
safe public activity metadata
```

Definitions and the surrounding capability/context/Skill/provider JSON contracts are
deeply normalized/copied so nested mutable schema or metadata cannot change an
accepted contract after registration. P8 uses immutable `FrozenDict`/`FrozenList`
wrappers that still satisfy normal `isinstance(value, dict/list)` checks and explicit
thaw helpers for transport serialization.

Group/guard exceptions fail closed: a failed availability check makes the capability
unavailable and does not expose the underlying exception to the model.

There is no generic arbitrary SQL, Python, shell, sudo or unrestricted ORM-method
execution surface.

## 3. Provider extension boundary

Trusted installed Odoo addons may contribute a `CapabilityProvider` discovered from
the active Odoo registry marker. The provider API is versioned:

```text
CAPABILITY_PROVIDER_API_VERSION = "1"
```

Core namespaces such as `odoo.*`, `assistant.*` and `host.*` are reserved unless the
provider is explicitly owned by core. The same namespace rule applies to contributed
capabilities/Skills/ContextProviders/EvidenceProviders.

Current provider composition can include:

```text
CapabilityProvider
  +-- CapabilityDefinition(s)
  +-- SkillDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
  +-- immutable provider metadata
```

API mismatch, loader failure, identity/capability collisions, dependency/version
errors and dependency cycles are provider-boundary failures. Optional failures are
attributed and isolated so a broken extension does not remove healthy sibling
providers or the core catalog. Required providers fail closed.

Sanitized provider introspection includes provider id, provider version, API version,
optional/required state, capability/Skill/Context/Evidence counts and an `error_code`.
It never exposes raw exceptions, stack traces, secrets or arbitrary host paths.

## 4. Effective registry and executor

The effective path is:

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

Business handlers use the effective Odoo user with `su=False`.

## 5. Reads and effects

READ/analysis calls may iterate under exploration/cost/latency/output budgets and
current Odoo ACLs.

Effects remain host controlled:

```text
model proposes typed step
 -> host resolves CapabilityDefinition
 -> validate args + eligibility
 -> preview/preconditions
 -> policy
 -> approval when policy requires it
 -> durable write barrier
 -> execute
 -> verify
 -> receipt/recovery
```

Approval is policy/autonomy-driven. A full-control mode can avoid redundant
confirmation for an operation already permitted to the effective user when its
trusted policy allows auto-execution. Autonomy never expands ACLs/record rules,
field access, companies or capability authority.

Ambiguous effects are not retried blindly.

## 6. Skills / Bundles

`SkillDefinition` groups semantic behavior above atomic executable capabilities. It
may contain:

```text
description/title/version
trusted instructions/examples
capability selectors
ContextProvider selectors
EvidenceProvider selectors
activation/configuration metadata
eval ownership
```

Skills never execute and never own ACL/policy/approval. Active Skill instructions are
trusted installed-code guidance; every operation still resolves through the effective
capability registry/executor.

The product exposes one global Assistant; Skills are not separate user-facing bots.

## 7. ContextProvider

A `ContextProvider` supplies bounded just-in-time contextual data. Its output is
deeply frozen untrusted contextual data and cannot:

- register or reveal hidden capabilities;
- change policy;
- grant groups/permissions;
- approve effects;
- convert itself into trusted instructions.

Context is resolved progressively instead of dumping the whole installation into
every model call.

## 8. EvidenceProvider

P8 adds `EvidenceProvider` as a first-class non-executable resource on the same
extension boundary.

The shared Evidence layer includes:

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

Search returns bounded refs. Fetch resolves a logical ref and rechecks provider
identity, current access scope, fingerprint/freshness and output bounds.

Evidence is data. It can support a conclusion but never changes capability
availability, product profile, policy or approval.

The initial ledger is bounded to 64 refs, 16 selected excerpts, 8 KiB per excerpt and
64 KiB total. It stores enough provenance/freshness for continuation and citations,
not a second corpus or raw log/source dump. The current live wrapper keeps a
turn-scoped ledger; its snapshot is serializable/versioned but durable reconnect
restoration is not claimed yet.

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
module/repository HOW_TO     -> README/docs/manifest/source/scripts + install state
current external fact        -> web when policy/context allows
repository preflight         -> web/repo metadata + bounded static inspection
```

The current live decision seam is:

```text
AssistantExtensionDecisionEngine
 -> effective EvidenceProvider IDs
 -> question-sensitive routing
 -> bounded AssistantEvidenceDecisionEngine search/fetch
 -> bounded turn EvidenceLedger
 -> host_assistant_evidence   # sanitized structure/status only
 -> assistant_evidence        # untrusted ref/excerpt/data
 -> reasoning provider
```

The Codex adapter only maps that provider-neutral trust partition. Retrieved content,
including prompt-injection text, never becomes host/Skill instructions or authority.
The model may reason over it and the host may require local evidence for
installation-specific or safety-critical claims.

## 10. Runtime inventory Evidence

The first real provider is `assistant.runtime_inventory`. It derives bounded current
installation Evidence directly from the effective Odoo Environment:

```text
Odoo release/edition
hashed database identity
installed modules + safe version metadata
registry fingerprint
visibility = user | technical
```

It exposes no absolute source roots, raw database name, credentials, commands or
mutable business snapshots. A changed fingerprint is returned as stale Evidence.
The retired HTTP callback, addon machine-auth primitive and residual addon inventory
service are not used by this provider.

## 11. EffectiveAssistantManifest

`EffectiveAssistantManifest` is a projection of current effective host state, not an
authority registry. It includes effective provider/features, active Skills,
model-visible capabilities, ContextProviders and the existing
`evidence_provider_ids` seam plus sanitized health/availability metadata.

The admin/settings projection also derives effective available Evidence-provider IDs
from the same catalog. Do not place retrieved Evidence content or host-only details in
the manifest.

## 12. Product profiles

Product-facing profile values are exactly:

```text
user
technical
```

Older internal `business`/`developer`-style values remain only as compatibility
implementation detail and normalize unambiguously before public projection.

The future Technical/host broker is a privilege execution boundary, not a third human
profile. Profile projection itself grants no permission.

## 13. Progressive disclosure

The framework models:

```text
discovered -> available -> revealed -> active
```

The current product may remain eager for ordinary capability schemas. Lazy/on-demand
disclosure is promoted only when evals show equal-or-better task/tool-selection
quality and a useful context/latency/cost improvement.

Pydantic AI/FastMCP style provider/bundle/disclosure patterns remain references, not
runtime dependencies.

## 14. Invocation surfaces

Chat is one consumer of the same contract. Future MCP, automations, AI fields,
context launchers or other surfaces should reuse:

```text
CapabilityDefinition
CapabilityRegistry / CapabilityExecutor
Skill / Context / Evidence contracts
policy / ACL / profile / budgets
turn/effect/audit infrastructure where applicable
```

A new surface may have a different effective projection, but not a divergent authority
list.

## 15. Future operation breadth

The long-term goal is **universal discovery + typed promotion**, not giving the model
the ORM or shell.

Future discovery may inventory menus/actions/views/buttons/wizards/server actions and
observable model methods as non-executable descriptors. Reviewed operations can then
be promoted to typed `CapabilityDefinition`s or contributed by the owning addon.

Repository/module/service operations similarly require explicit contracts,
preconditions, risk/policy, verification and recovery. Arbitrary repositories may be
candidates after bounded preflight; an allowlist is optional policy/trust input, not a
universal execution authority.

## 16. Security checklist

Every new executable capability must answer:

1. What exact operation is allowed?
2. What schemas and byte/record/time/call limits bound it?
3. What effective user/company/groups/profile apply?
4. Is returned content host fact or untrusted Evidence/data?
5. What risk/effect class applies?
6. What preview/approval policy applies at each autonomy level?
7. How is success verified?
8. What happens on timeout/cancel/restart?
9. Is retry/reconstruction/reversion actually safe?
10. What public activity is safe to expose?
11. What deterministic/product/real gates block promotion?

## 17. Validation status

P7 is **COMPLETE / ACCEPTED** at `092ac57`.

The reconciled P8.0 + P8.1/P8.2 checkpoint, including the first live
provider-neutral Evidence search/fetch/trust projection, is implemented on `main`.
Its focused dependency-light/Odoo checks and P8 real gates remain unexecuted.
Implementation presence is not P8 acceptance.

See:

- `EVIDENCE_ARCHITECTURE.md`
- `OBSERVABILITY_ARCHITECTURE.md`
- `research/P8_EVIDENCE_CORE_IMPLEMENTATION.md`
- `research/P8_FOCUSED_VALIDATION_RUNBOOK.md`
- `research/EXECUTION_STATE.md`
