# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning and deterministic Odoo/host execution.

`PRODUCT_VISION.md` defines the target product. This document defines the capability boundary that current and future implementations must preserve.

## 1. Core principle

Declare an executable operation once as a `CapabilityDefinition`, then derive reasoning, planning, diagnostics, Settings and future transport views from the same trusted definition.

Do not create separate registries for chat tools, actions, MCP, automations or future invocation surfaces when they represent the same operation.

The model may be cognitively broad. **Authority remains explicit.** Naming a capability, Python function, ORM method, shell command or SQL statement does not make it executable.

## 2. Atomic definition

The exact current dataclass/code is authoritative. Conceptually a capability includes:

```text
stable id/name + version
title / model-facing description / user-facing description
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
optional public activity descriptor
```

The handler is always registered by trusted installed code or by a separately designed declarative/UI mechanism. It is never inferred from model-generated text.

## 3. Current provider package

Current core providers are:

```text
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

The current discovery path is intentionally scoped. Third-party `CapabilityProvider` discovery is target work in the gated roadmap, not an implementation claim.

## 4. Registry and effective catalog

`CapabilityRegistry` is the authority for effective availability. It resolves definitions and filters by host-known state such as:

```text
installed provider/module
configuration health
enablement
user/groups/companies
technical profile
capability guards/dependencies
invocation surface
run context
provider feature support where relevant
```

Consumers receive projections, not handlers.

Target projections include:

```text
reasoning catalog
planning catalog
diagnostics/settings catalog
public Assistant manifest
future MCP/automation surface catalog
```

A capability hidden/disabled/unauthorized by the host remains unavailable even if the user explicitly asks the model to call it.

## 5. Executor

`CapabilityExecutor` executes only a resolved, effective definition with validated arguments/context. It owns schema, availability, budgets and policy integration around the trusted handler.

Business handlers use the effective Odoo user and `su=False` unless a capability is explicitly classified as host-internal/privileged and is implemented through a separate authority boundary. `sudo()` is not a shortcut for model-visible business authority.

## 6. Reads vs effects

READ/analysis operations may be broad and iterative but remain bounded by exploration/cost/latency budgets and Odoo ACLs.

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

The future multi-step `EffectPlan` is a composition of typed capability steps; it is not arbitrary generated code.

## 7. Current generic Odoo providers

### Query

`odoo_query` performs schema-first bounded live business reads/aggregates under current Odoo permissions. Frequently changing business truth should stay live rather than becoming an indexed RAG snapshot.

### Actions

`odoo_actions` performs explicit supported effects. Generic arbitrary method execution is intentionally absent.

### Batch

`odoo_batch` applies bounded collection operations under the same authority/policy path. Large imports are a future staged workflow rather than thousands of unconstrained model-authored calls.

### Runtime

`odoo_runtime` exposes narrow current runtime information. Today it is not a filesystem/shell/secrets back door.

## 8. Technical and host capabilities

The framework is **not** permanently limited to CRUD/business operations.

An explicitly designed capability may encapsulate filesystem, process, service, configuration, network/API or other host operations if its authority boundary, input/output schema, technical profile, privilege model, preview/verification and recovery are defined.

Future examples:

```text
odoo.module.inspect/install/update
odoo.config.inspect/patch
source.find_symbol/read_excerpt
odoo.logs.search/read_context
host.service.status/restart
postgres.health/activity
web.search/fetch
```

Prefer high-level semantic capabilities over generic shell because they are easier to validate/test/policy/verify.

A future generic command capability, if needed, is a Developer-only high-risk fallback. It requires its own sandbox/allowlist/path/env/output/timeout/audit/approval design and must not grant broad root authority to the Odoo process.

Direct source-code writes are later gated work: stage patch -> diff -> test -> deploy/verify, not unrestricted production editing.

## 9. Extension architecture

Target composition:

```text
CapabilityProvider
  +-- Skill / Bundle
  +-- CapabilityDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
  +-- configuration metadata
```

### CapabilityProvider

A trusted installed addon contributes contracts without editing core. Provider identity/version and conflicts are deterministic. One broken optional provider must not corrupt the core catalog.

### Skill / Bundle

A Skill gives semantic grouping and progressive discovery. It may contain descriptions/examples, instructions, capability selectors, context/evidence selectors and activation/configuration metadata.

A Skill **does not execute anything** and does not own permissions. There is still one global user-facing Assistant.

### ContextProvider

Provides bounded just-in-time context for reasoning, such as module/view/domain context. Context is data, never authorization.

### EvidenceProvider

Searches/fetches normalized Evidence from sources such as source/XML, logs, documents or web. Retrieved content cannot register capabilities or modify policy.

## 10. Self-awareness and `EffectiveAssistantManifest`

The future Assistant self-description must be derived from effective host state, not a static prompt.

Conceptually:

```text
provider + feature support
technical access profile
effective skills
available/revealed capabilities
context/evidence/knowledge sources
configuration health
safe reason for known unavailable features
```

This allows natural responses such as:

> Puedo analizar Ventas y CRM y consultar código/logs con tu perfil actual. La modificación de configuración del servidor está instalada pero deshabilitada para este usuario.

The manifest is a projection of authority/configuration; it does not create authority itself.

## 11. Progressive disclosure

Large catalogs must not force hundreds of detailed schemas into every provider turn.

Target lifecycle:

```text
discovered -> available -> revealed -> active
```

The model can retain high-level awareness of Skills/namespaces while loading detailed definitions only when needed. Keep common discovery/query capabilities eager where evals show that improves quality.

Progressive disclosure is accepted only if task success/tool-selection quality remains equal or better under the permanent eval suite. Token reduction alone is insufficient.

OpenAI Agents namespaces/tool search and Pydantic-style capability bundles are useful reference patterns; neither is required as a second runtime dependency.

## 12. UI/declarative capabilities

The framework should eventually allow safe simpler configuration from Odoo UI in addition to trusted Python code.

Good candidates are declarative tools backed by already-authorized mechanisms such as:

```text
Odoo Server Action
bounded HTTP/API operation
field/model mapping
schema + description + policy metadata
```

OCA's `ai_tool`/AI Server Action work is a useful pattern for user-configurable tools.

Arbitrary Python stored in database is a materially higher-risk feature. If supported, it belongs behind Developer/admin-only policy and explicit security tests; it is not the normal extension mechanism.

## 13. Invocation surfaces

Chat is one surface over the same catalog. Future MCP, automation, AI fields or context launchers reuse:

```text
CapabilityDefinition
CapabilityRegistry
CapabilityExecutor
policy/ACL/technical profile
Evidence/Context contracts
```

Each surface may receive a different **effective** catalog based on context, but there is no second divergent list of tools.

OCA `ai_tool` and Apexive's chat/MCP tool reuse demonstrate the practical value of this pattern.

## 14. Security checklist for every new capability

Every new executable definition must answer:

1. What exact operation is allowed?
2. What schemas and byte/record/time limits bound it?
3. What effective user/company/technical-profile permissions apply?
4. Is returned content trusted host fact or untrusted evidence/data?
5. What risk/effect class applies?
6. What preview/approval is needed?
7. How is success verified?
8. What happens on timeout/cancel/restart?
9. Can the operation be safely retried, reconstructed or only reviewed?
10. What public activity is safe to expose?
11. What deterministic/agentic/real tests block promotion?

## 15. Testing requirements

New framework layers are not complete until tests prove:

- discovery/enable/disable/uninstall;
- duplicate provider/capability conflict handling;
- effective ACL/technical-profile filtering;
- schema failures fail closed;
- disabled/hidden tool cannot be invoked by name;
- surface adapters do not change authority;
- progressive disclosure does not materially regress selection;
- one optional provider failure does not break core capabilities;
- provider/tool descriptions cannot alter host policy.

Named hard real gates are defined in `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` and `research/REAL_ENV_VALIDATION_PROTOCOL.md`.
