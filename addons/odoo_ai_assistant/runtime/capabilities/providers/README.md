# Core capability providers

This folder contains executable capabilities shipped by the core addon. Core provider
modules are discovered deterministically; the agent runtime must not hard-code a
parallel list.

Trusted installed addons may also contribute `CapabilityProvider` markers through the
Odoo registry. That P7 extension API is current and versioned; do not simulate it by
scanning arbitrary Python packages on the host.

## Current core families

```text
odoo_query           live schema-first reads / aggregates / bounded identity selection
odoo_actions         explicit effects + preview/verification
odoo_batch           bounded collection effects
odoo_bulk            uncommon exact high-volume selection/delete path
odoo_workflows       bounded typed related-record workflows
odoo_runtime         narrow effective runtime facts
odoo_navigation      host-resolved contextual navigation
odoo_unarchive       explicit unarchive effect
odoo_compensations   HOST-only verified compensators
assistant_preferences conversation preference operations
```

The exact current files/definitions in code are authoritative.

## Generic vs semantic operations

Generic schema/query/create/patch primitives are useful horizontal fallback. Repeated
business workflows should prefer semantic capabilities that capture eligibility,
preconditions and verification.

Example:

```text
frequent business workflow:
    odoo.sale_order.confirm

uncommon safe data work:
    discover effective schema -> bounded generic operation
```

Do not expose arbitrary ORM methods merely to increase breadth.

## Extension providers

A trusted installed addon can contribute through `CapabilityProvider`:

```text
CapabilityDefinition(s)
SkillDefinition(s)
ContextProvider(s)
EvidenceProvider(s)
immutable metadata
```

Rules:

- `CAPABILITY_PROVIDER_API_VERSION = "1"` is checked host-side;
- provider/definition IDs must be stable and unique;
- `odoo.*`, `assistant.*` and `host.*` are reserved core namespaces;
- optional-provider/guard/resource failures are isolated;
- required providers may fail closed;
- schemas/metadata are normalized/deeply immutable after acceptance;
- a provider cannot bypass ACL/policy/approval/verification.

Domain addons such as future `odoo_ai_assistant_sale` or
`odoo_ai_assistant_account` should use this boundary rather than editing a central
registry. Their internal packaging must preserve a one-product installation
experience for customers.

## Evidence resources

P8 adds Evidence resources without turning them into executable capabilities.
`EvidenceProvider`s are composed only from providers accepted by the extension
boundary and use `EvidenceProviderCatalog` for availability/search/fetch isolation.

The built-in `assistant.runtime_inventory` provider lives outside this executable
`providers/` folder because it is a non-executable Evidence resource. It exposes a
bounded effective installation projection and never grants capability authority.

Skills can select Evidence provider IDs; the existing
`EffectiveAssistantManifest.evidence_provider_ids` seam projects sanitized effective
IDs, not retrieved content.

## Adding a core executable provider

1. Keep operations cohesive by domain.
2. Declare a trusted `CapabilityDefinition` with explicit schemas.
3. Write meaningful model-facing descriptions for model-visible exposures.
4. Bound records, bytes, calls, time and output.
5. Use the effective Odoo user with `su=False` for business access.
6. Classify risk/effect correctly.
7. Add preview/preconditions and verification for effects.
8. Add focused deterministic tests and agentic eval ownership where selection matters.
9. Verify discovery/conflict/optional-failure behavior.
10. If reversible, provide/test a real compensator rather than assuming an inverse.
11. If returning navigation/reference data, keep discovery separate from final host revalidation.
12. Do not add a second registry or provider-specific authority path.

## Business actions

As product coverage grows, domain packs should add small, versioned semantic actions
rather than hundreds of thin CRUD aliases. Each action should define intent,
eligibility, preview, risk/policy, execution and verification.

The same framework supports both generic fallback and high-value domain semantics.

## Provider does not mean model provider

“Capability provider” here means trusted installed code contributing Assistant
resources. It is different from the reasoning/model provider (Codex today).
