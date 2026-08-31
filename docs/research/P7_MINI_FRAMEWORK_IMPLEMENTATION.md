# Phase 7 implementation record — mini-framework and feature negotiation

Date: 2026-08-31  
Phase: 7 — mini-framework, feature negotiation and Assistant self-awareness  
State: `IMPLEMENTATION_ADVANCING / VALIDATION_DEFERRED_BY_USER`

## Sequencing decision

The earlier checkpoint paused live P7 work behind Product Behavior Evals v1. On 2026-08-31 the user explicitly
requested continued implementation and chose to validate the accumulated gates later. The gate is therefore no longer
a **sequencing** blocker, but it is still a required **acceptance/promotion** gate. No unexecuted validation is treated
as PASS in this record.

## Architecture retained

```text
trusted installed addon
 -> CapabilityProvider
 -> CapabilityBundle/Skill + ContextProvider resources
 -> effective CapabilityRegistry
 -> CapabilityDefinition
 -> existing executor / policy / ACL / approval / verification authority
```

`CapabilityDefinition` remains the only atomic executable contract. Skills organize behavior; ContextProviders add
bounded data; neither grants authority.

## P7.1 — live CapabilityProvider wiring

The P7.1 foundation already provided stable provider identity/version, deterministic Odoo-registry discovery,
optional-provider isolation, conflict rejection, provider provenance and `discover_capabilities_for_env(env)`.

The effective installed-addon catalog is now used by the current live Odoo surfaces:

```text
addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py
addons/odoo_ai_assistant/models/runtime_settings.py
addons/odoo_ai_assistant/models/turn_control.py
```

Specifically:

- live turns compose the registry from the effective Odoo registry before resolving settings/policy;
- generic Settings catalog and capability configuration resolve installed-provider capabilities too;
- reversion/compensation and reversion eligibility use the same effective registry;
- no provider can bypass `CapabilityExecutor`, host policy, current-user ACL/record rules, approval or verification.

Addon version is now `18.0.13.7.0` for this live-catalog behavior change.

## P7.2 — Skill/Bundle contracts

Added `runtime/capabilities/skills.py`:

```text
SkillDefinition
SkillCatalog
```

A Skill can declare:

- stable id/version/title/description;
- trusted behavior instructions and bounded examples;
- capability selectors;
- ContextProvider selectors;
- EvidenceProvider selectors;
- activation/configuration metadata;
- eval owner;
- default enablement with host-side override semantics.

Selectors support exact identities and `namespace.*`. A Skill never creates or authorizes an executable handler.

## P7.3 — ContextProvider contracts and resource composition

Added `runtime/capabilities/context.py` and `runtime/capabilities/extensions.py`.

`ContextProvider` supplies bounded JSON JIT context with:

- stable identity/version;
- explicit output byte limit;
- host-side enablement;
- optional failure isolation;
- sanitized status codes;
- no permission or policy semantics.

`CapabilityProvider` can now contribute `skills` and `context_providers` alongside executable definitions.

`AssistantExtensionCatalog` composes those non-executable resources only after the corresponding capability provider
has been accepted by the host registry. A provider whose executable contract failed cannot smuggle Skill instructions
or ContextProviders into the turn. Optional resource identity collisions are fail-isolated rather than shadowing an
existing resource; required collisions fail closed.

`AssistantExtensionCatalog.activate(...)` resolves active Skills and only the JIT ContextProviders selected by those
Skills. `ActiveAssistantExtensions` keeps trusted Skill guidance separate from untrusted JIT context data.

The remaining P7.2/P7.3 product step is to inject this active resource projection into the live provider decision
context while preserving the current `host_contract` vs `untrusted_data` split.

## P7.4 — ProviderProfile

Added `runtime/capabilities/features.py` with an explicit complete feature matrix:

```text
structured_output
 tool_calling
 answer_streaming
 vision
 file_input
 web
 large_context
```

Every feature is `native`, `emulated` or `unavailable`; unavailable states require a safe reason code. Capacity fields
include context window, max output and parallel-request limits when known.

The current Codex adapter is **not yet bound** to a product-level ProviderProfile in this checkpoint. That binding must
be derived from actual adapter/model behavior rather than guessed from generic provider knowledge.

## P7.5 — EffectiveAssistantManifest

Added `runtime/capabilities/manifest.py`.

The manifest derives a safe projection of:

- provider profile;
- technical profile;
- effective Skills;
- capability identity/exposure/effect/risk/provider provenance;
- available/revealed state;
- ContextProvider/evidence-provider identities;
- provider/configuration health;
- known unavailable features and safe reason codes.

It is explicitly a projection, not a second registry. Handlers and Skill instructions are not exposed in the browser
payload.

## P7.6 — technical profile skeleton

`TechnicalAccessProfile` currently distinguishes:

```text
BUSINESS
DEVELOPER
```

This is descriptive reach only. It does not grant shell, SQL, Python, sudo, unrestricted ORM or any other privileged
host operation.

## P7.7 — progressive disclosure contract

Added `runtime/capabilities/disclosure.py` with:

```text
DisclosurePolicy
CapabilityDisclosureSnapshot
available -> revealed -> active
```

Disclosure is **disabled by default**. With it disabled, every currently available capability is revealed exactly as
before. Lazy reveal is only activated explicitly and always preserves host-side validation; an unrevealed capability
never becomes executable merely because the model names it.

This is intentional: the Atlas/roadmap requires progressive disclosure when catalog-scale evals show pressure, not as
an unmeasured optimization.

## New dependency-light coverage prepared

```text
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_extension_composition.py
```

They cover the new contract layer, including Skill selection, bounded ContextProviders, complete ProviderProfile
matrices, derived manifest behavior, disclosure semantics, provider resource acceptance and collision/failure
isolation.

These tests were added but **have not been executed after the latest P7 changes** because validation is deferred by
user direction.

## References and rationale

The design follows the Project Atlas and Benchmark direction: keep `CapabilityDefinition` as the strict host-owned
unit, add provider/bundle/context composition around it, and model `discovered -> available -> revealed -> active`
without adding Pydantic AI/FastMCP as a second runtime. Pydantic AI contributes the bundle/progressive-disclosure
pattern; FastMCP the provider abstraction; Apexive proves Odoo-native extension discovery is practical. Odoo's
Agent/Skill/Tool/Source separation remains the product-level reference.

## Invariants

- Odoo remains operational/persistence authority.
- Business operations use effective-user `su=False`.
- Provider discovery is limited to trusted installed Odoo registry code.
- Capability/resource identity conflicts never silently shadow existing identities.
- Skills and context cannot grant authority.
- Context is data and remains prompt-injection capable/untrusted by default.
- Provider metadata never replaces ACL/policy/approval/verification.
- No arbitrary host-code/package/filesystem discovery is introduced.
- Progressive disclosure changes model visibility, not host executability.

## Remaining implementation before Phase-7 validation run

1. Inject active Skill guidance and selected JIT ContextProvider data into the provider decision seam with an explicit
   trusted-guidance vs untrusted-data contract.
2. Bind the concrete Codex/model adapter to `ProviderProfile` using only behavior the runtime can actually support and
   explain safely.
3. Expose/use `EffectiveAssistantManifest` for self-awareness (`¿qué puedes hacer?`) and admin diagnostics without
   duplicating authority.
4. Add the trusted installed test-addon fixture (Skill + READ + PLAN + ContextProvider + configuration).
5. Add synthetic 100+ capability disclosure coverage and explicit hidden-call denial coverage.

## Validation accumulated for later

Product Behavior Evals v1 remains pending, including focused/static/Odoo/HOOT validation plus real SMOKE/FULL.

Phase-7 real gates remain pending:

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

No gate above is claimed by this implementation record.
