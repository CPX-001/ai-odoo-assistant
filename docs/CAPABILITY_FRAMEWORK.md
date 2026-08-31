# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning and deterministic Odoo/host
execution. `PRODUCT_VISION.md` defines the target product; this document defines the current capability boundary and
the extension direction that must preserve it.

## 1. Core principle

Declare an executable operation once as a `CapabilityDefinition`, then derive reasoning, planning, diagnostics,
Settings and future transport views from the same trusted definition.

Do not create separate registries for chat tools, actions, MCP, automations or future invocation surfaces when they
represent the same operation.

The model may be cognitively broad. **Authority remains explicit.** Naming a capability, Python function, ORM method,
shell command or SQL statement does not make it executable.

## 2. Atomic executable definition

The exact current dataclass/code is authoritative. Conceptually a `CapabilityDefinition` includes:

```text
stable id/name + version
title / model-facing description
input JSON Schema
output JSON Schema
risk + effect classification
exposure: reasoning | plan | host
approval semantics
groups / guards / dependencies / configuration
budgets / record-byte-time limits
trusted handler
optional preview/preconditions
optional verification
```

The handler is always registered by trusted installed code or by a separately designed declarative/UI mechanism. It
is never inferred from model-generated text.

`CapabilityDefinition` remains the atomic executable authority even after Phase-7 provider/Skill/context composition.

## 3. Current provider discovery

Core provider modules remain package-discovered and cached. Current built-in areas include query, actions, batch,
runtime and the other provider modules present in `runtime/capabilities/providers/`.

Phase 7 adds an Odoo-native installed-addon extension point:

```text
trusted installed model class
  _odoo_ai_capability_provider = CapabilityProvider(...)
            |
            v
discover_odoo_capability_providers(env)
            |
            v
compose_capability_registry(...)
            |
            v
discover_capabilities_for_env(env)
```

The live host loop, generic Settings capability catalog/configuration and reversion/compensation paths now use the
environment-aware effective catalog.

Discovery is intentionally restricted to code materialized in the active Odoo registry. It does not scan arbitrary
host Python packages or the filesystem.

## 4. Registry and effective catalog

`CapabilityRegistry` is the executable source of truth for effective availability. It resolves definitions and filters
by host-known state such as:

```text
installed provider/module
configuration health
enablement
user/groups/companies
capability guards/dependencies
invocation/run context
```

Provider provenance and sanitized provider status are retained by the registry. Optional provider failure cannot
silently replace or remove the core catalog; identity/executor collisions are rejected rather than shadowed.

Consumers receive projections, not handlers.

Current/target projections include:

```text
reasoning catalog
planning catalog
diagnostics/settings catalog
EffectiveAssistantManifest
future MCP/automation surface catalog
```

A capability hidden/disabled/unauthorized by the host remains unavailable even if the user explicitly asks the model
to call it.

## 5. Executor and authority

`CapabilityExecutor` executes only a resolved, effective definition with validated arguments/context. It owns schema,
availability, budgets and policy integration around the trusted handler.

Business handlers use the effective Odoo user and `su=False`. `sudo()` is not a shortcut for model-visible business
authority.

Effects remain host-controlled:

```text
model proposes
 -> host resolves definition
 -> validate arguments
 -> preview/preconditions
 -> policy/approval
 -> durable write barrier
 -> execute
 -> verify
 -> receipt/recovery state
```

An `EffectPlan` is a composition of typed capability steps, never arbitrary generated code.

## 6. Phase-7 extension architecture

Current composition direction is:

```text
CapabilityProvider
  +-- CapabilityDefinition(s)      # executable authority stays here
  +-- SkillDefinition(s)           # behavior/grouping, no authority
  +-- ContextProvider(s)           # bounded JIT data, no authority
  +-- provider metadata

AssistantExtensionCatalog
  +-- SkillCatalog
  +-- ContextProviderCatalog
  +-- sanitized extension status
```

### CapabilityProvider

A trusted installed addon contributes definitions/resources without editing core. Provider identity/version and
conflicts are deterministic. Optional provider failures are isolated; required provider failures fail closed.

A provider whose executable contract was rejected does not get to inject Skill instructions or ContextProviders.

### Skill / Bundle

`SkillDefinition` groups semantic behavior. It can contain:

```text
stable id/version
description/title
instructions + bounded examples
capability selectors
ContextProvider selectors
EvidenceProvider selectors
activation/configuration metadata
eval ownership
```

Selectors support exact identities and namespace patterns such as `sales.*`.

A Skill **does not execute anything** and does not own permissions. It may organize or guide use of capabilities that
are already effective for the current host context.

### ContextProvider

`ContextProvider` supplies bounded JSON just-in-time context. The host controls enablement and output limits; optional
provider failures are sanitized/fail-isolated.

Context is always data. A record, document, source excerpt, log line or ContextProvider payload can be malicious or
prompt-injected and cannot redefine policy or grant execution authority.

### Active resource resolution

`AssistantExtensionCatalog.activate(...)` resolves active Skills against the effective capabilities/context/evidence
identities, then collects only the JIT ContextProviders selected by those Skills.

`ActiveAssistantExtensions` keeps trusted installed-code Skill guidance separate from untrusted context data.

At the current Phase-7 checkpoint this contract/composition exists, while injection into the live Codex decision input
is still pending.

## 7. Provider feature negotiation

`ProviderProfile` and `ProviderFeatureSupport` model provider/runtime capability explicitly. Every supported feature is:

```text
native | emulated | unavailable
```

The current matrix includes at least:

```text
structured_output
tool_calling
answer_streaming
vision
file_input
web
large_context
```

Known capacity can include context-window, max-output and parallel-request characteristics.

Do not infer this matrix from marketing or a generic provider name. Bind the concrete configured adapter/model only to
behavior the runtime actually supports. The Codex product profile is not yet exposed at the current checkpoint.

## 8. EffectiveAssistantManifest and technical profile

`EffectiveAssistantManifest` is implemented as a derived projection of current host state. It can describe:

```text
provider/features
technical profile
effective skills
available/revealed capabilities
context/evidence providers
configuration/provider health
safe reasons for known unavailable features
```

The browser projection omits executable handlers and Skill instructions. The manifest cannot create authority; it can
only describe what the host already resolved.

`TechnicalAccessProfile` currently defines the descriptive skeleton:

```text
BUSINESS
DEVELOPER
```

This does **not** grant privileged host operations. Shell, SQL, Python, sudo, unrestricted ORM and host administration
remain unavailable unless separately designed as explicit high-risk capabilities later.

## 9. Progressive disclosure

Phase 7 models:

```text
discovered -> available -> revealed -> active
```

`DisclosurePolicy` and `CapabilityDisclosureSnapshot` implement the `available/revealed/active` projection. Disclosure
is disabled by default: current behavior remains eager until permanent evals/catalog scale justify hiding detailed
schemas.

When enabled, disclosure changes what the provider sees, not what the host can execute. Host-side registry lookup,
availability, policy and approval remain mandatory.

Pydantic-style on-demand capabilities and OpenAI tool-search/namespaces are reference patterns; neither is required as
a second runtime dependency.

## 10. Current generic Odoo capability areas

### Query

Schema-first bounded live business reads/aggregates under current Odoo permissions. Frequently changing business truth
stays live rather than becoming a stale RAG snapshot.

### Actions

Explicit supported effects. Generic arbitrary method execution is intentionally absent.

### Batch

Bounded collection operations under the same authority/policy path. Large imports should become staged jobs rather
than thousands of unconstrained model-authored calls.

### Runtime/source/diagnostic reads

Narrow, bounded runtime and source evidence may be exposed through explicit capabilities. They are not filesystem,
shell or secrets back doors.

## 11. Technical and future host capabilities

The framework is not permanently limited to CRUD/business operations. A separately designed capability may encapsulate
filesystem, process, service, configuration, network/API or other host operations if its authority boundary,
input/output schema, technical profile, privilege model, preview/verification and recovery are explicit.

Prefer high-level semantic capabilities over generic shell because they are easier to validate, test, policy and
verify. Direct source-code writes remain later gated work: stage patch -> diff -> test -> deploy/verify, not
unrestricted production editing.

## 12. EvidenceProvider and retrieval direction

`EvidenceProvider` remains a later layer. It will search/fetch normalized evidence from source/XML, logs, documents,
web and other sources behind provenance/trust/ACL boundaries.

Do not collapse all evidence into vector RAG. Runtime/schema/source/document/log evidence may require different
retrieval mechanisms.

Retrieved content cannot register capabilities, grant permissions or modify policy.

## 13. UI/declarative capabilities

The framework should eventually allow safe simpler configuration from Odoo UI in addition to trusted Python code.
Good candidates are declarative tools backed by already-authorized mechanisms such as Odoo Server Actions, bounded
HTTP/API operations or field/model mappings.

Arbitrary Python stored in the database is materially higher risk and is not the normal extension mechanism.

## 14. Invocation surfaces

Chat is one surface over the same catalog. Future MCP, automation, AI fields or context launchers reuse:

```text
CapabilityDefinition
CapabilityRegistry
CapabilityExecutor
provider/Skill/context composition
policy/ACL/technical profile
Evidence contracts
```

Each surface may receive a different **effective** catalog based on context, but there is no second divergent list of
tools.

## 15. Security checklist for every new executable capability

Every new definition must answer:

1. What exact operation is allowed?
2. What schemas and byte/record/time limits bound it?
3. What effective user/company/technical-profile permissions apply?
4. Is returned content trusted host fact or untrusted evidence/data?
5. What risk/effect class applies?
6. What preview/approval is needed?
7. How is success verified?
8. What happens on timeout, retry, restart or ambiguous effect?
9. Can this definition/resource collide with an installed provider identity?
10. Does any Skill/Context/Evidence text attempt to become authority rather than data/guidance?

## 16. Phase-7 validation state

Implementation is currently allowed to advance with validation deferred by explicit user direction. This does not
waive promotion gates. See:

```text
docs/research/EXECUTION_STATE.md
docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md
docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md
```

The Phase-7 real gates and the Product Behavior SMOKE/FULL runs remain pending until actually executed.
