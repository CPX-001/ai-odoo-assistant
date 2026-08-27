# Capability Framework

The Capability Framework is the host-owned contract between probabilistic reasoning and deterministic Odoo execution.

## Core principle

Declare an executable operation once as a `CapabilityDefinition`, then derive the views needed by reasoning, planning, diagnostics and future transports from that same definition.

Do not create separate registries for chat tools, actions, MCP tools or automations when they represent the same operation.

## Atomic definition

A capability definition carries both model-facing and host-facing metadata. The exact dataclass/code is authoritative, but conceptually it includes:

```text
stable id/name
summary/description
input JSON Schema
output JSON Schema
risk
side-effect/effect classification
approval semantics
groups/guards/dependencies
budgets/limits
handler
```

The handler is never inferred from a model-generated name or arbitrary Odoo method. Registration is explicit/deterministic through trusted installed code.

## Decorator and discovery

Core providers define capabilities with the framework decorator and are discovered by `CapabilityRegistry`. Current provider modules are:

- `odoo_query`;
- `odoo_actions`;
- `odoo_batch`;
- `odoo_runtime`.

Discovery today is intentionally scoped to the installed core provider package. That keeps the current surface deterministic but is not yet the desired third-party extension model.

## Registry

The registry is the source of truth for effective availability. It resolves definitions and filters by host-known conditions such as groups, guards, dependencies/configuration and run context.

Consumers use purpose-specific projections, not handler objects:

- reasoning view: enough description/schema for tool selection;
- planning view: enough effect/risk/dependency metadata for plan validation;
- diagnostics view: sanitized availability/issue metadata;
- future transport adapters: generated from the same effective definition.

The model cannot make an unavailable definition available by naming it.

## Executor

`CapabilityExecutor` receives a resolved definition and validated input/context. It enforces schema/availability/budget/policy checks around the trusted handler and normalizes capability errors/results.

Handlers must remain bounded and use the effective Odoo user for business access. A handler must not use `sudo()` or a technical service account as a shortcut around normal permissions unless an explicitly host-internal operation is separately designed and justified.

## Query provider

`odoo_query` implements schema-first, bounded business reads. Model/field/operator availability is derived from the live installation/user. Query limits are host constants, not prompt suggestions.

See `QUERY_CONTRACT.md`.

## Action provider

`odoo_actions` owns controlled effect semantics around effective write schema, previews/preconditions and verification. The framework deliberately does not expose arbitrary `execute_kw`/method execution.

Provider adapters must make the planning contract explicit: when the user's requested outcome is an Odoo state change that an available planning capability exactly supports, the reasoning provider is expected to ground the necessary model/record/schema/fields through read-only capabilities and emit the corresponding plan step. Returning a normal read-only answer with an empty plan does not satisfy that supported mutation request. This remains probabilistic model guidance, not host authority: the host does not infer write intent from prompt text, and every emitted step is still validated against the effective planning catalog, schema, policy, preview/approval and verification path.

## Batch provider

`odoo_batch` extends controlled effects to bounded collections without bypassing the same authority/policy model. Batch behavior should favor deterministic summaries/receipts and avoid hundreds of unconstrained model-authored writes.

## Runtime provider

`odoo_runtime` exposes only narrow runtime information needed by reasoning. Runtime metadata is not a back door to filesystem/shell/secrets.

## Extension direction

The project research uses the following conceptual model:

```text
CapabilityProvider
    -> CapabilityBundle / Skill
        -> CapabilityDefinition
```

This is **direction**, not current implementation.

- `CapabilityDefinition` remains the atomic executable/authority contract.
- A future `CapabilityProvider` should let trusted installed addons contribute definitions/bundles without editing the core package.
- A future `CapabilityBundle/Skill` should group instructions, capability selectors and activation metadata; it must not duplicate handlers or authorization.
- If the catalog becomes large, availability/disclosure can evolve toward `discovered -> available -> revealed -> active` and lazy loading.

Pydantic AI Capabilities/Toolsets and FastMCP Providers are useful references for composition/progressive disclosure, but importing either as a second agent runtime is not required.

## Security rules for new capabilities

Every new definition must answer:

1. What exact host operation is allowed?
2. What input/output schema bounds it?
3. What user/company/field permissions apply?
4. Is returned content trusted or untrusted data?
5. What risk/effect classification applies?
6. Is preview/approval required?
7. How is success verified?
8. What happens on timeout/retry/restart?
9. What budgets/record/byte limits prevent blast-radius growth?
10. What deterministic tests and agentic eval cover it?

Never add arbitrary SQL/Python/shell/sudo/unrestricted method execution merely to increase apparent agent flexibility.

## Compatibility/transport rule

If MCP, automation or another client is added later, implement an adapter over the effective catalog. Do not maintain a second list of tools with divergent permissions.
