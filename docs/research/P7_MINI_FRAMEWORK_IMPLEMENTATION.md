# Phase 7 implementation record — mini-framework and feature negotiation

Date: 2026-08-31  
Phase: 7 — mini-framework, feature negotiation and Assistant self-awareness  
State: `IMPLEMENTATION_COMPLETE / ACCEPTANCE_VALIDATION_PENDING`

## Meaning of this state

The implementation work planned for P7.1-P7.7 is now present on `main`. The user explicitly chose to defer the
accumulated validation and corrections until the end of the phase, so **no unexecuted deterministic, Odoo, product or
real gate is claimed PASS**. Phase 8 remains ineligible until the consolidated Phase-7 validation is green.

Implementation complete is therefore not the same as accepted/validated complete.

## Current composition

```text
trusted installed Odoo addon
 -> CapabilityProvider
    -> CapabilityDefinition(s)            executable authority unit
    -> SkillDefinition(s)                 trusted behavior guidance, no authority
    -> ContextProvider(s)                 bounded JIT data, no authority
 -> effective CapabilityRegistry
 -> AssistantExtensionCatalog
 -> EffectiveAssistantManifest
 -> provider-neutral AgentTurnService
 -> current Codex decision adapter
 -> CapabilityExecutor / policy / approval / verification
```

Odoo remains operational authority. Business handlers continue under the effective user with `su=False`; Skills,
provider metadata, manifests and JIT context cannot grant permission or effect authority.

## P7.1 — CapabilityProvider API

Implemented:

- deterministic provider id/version;
- trusted installed-addon discovery through the active Odoo registry;
- no arbitrary filesystem/package scanning;
- static/deferred provider definitions;
- provider provenance per capability;
- duplicate provider/capability/executor conflict rejection;
- optional-provider failure isolation;
- `discover_capabilities_for_env(env)` wired into the live host loop, Settings and reversion/compensation paths.

The existing core registry remains the base catalog. Installed extensions compose on top of it rather than replacing
it.

## P7.2 — Skill / Bundle

Implemented `SkillDefinition` / `SkillCatalog` with:

- stable identity/version/title/description;
- trusted instructions and examples;
- capability selectors;
- ContextProvider/EvidenceProvider selectors;
- activation/configuration metadata;
- eval ownership;
- provider provenance;
- deterministic activation from host-known effective identities.

Active Skill instructions are projected into the provider as trusted installed-code behavior guidance. They are
explicitly documented at the provider seam as **non-authoritative**: they cannot enable a capability, bypass ACLs,
approve a write or alter policy.

## P7.3 — ContextProvider

Implemented bounded JIT ContextProviders with:

- stable identity/version;
- deterministic enablement;
- JSON/bounds validation;
- optional-provider failure isolation;
- Skill-selective collection;
- safe status projection.

Live turns now activate only ContextProviders selected by active Skills. Their returned payload is placed in the
provider's **untrusted data** section, never in the host authority contract.

## P7.4 — ProviderProfile

Implemented provider-neutral feature negotiation with explicit:

```text
native | emulated | unavailable
```

for:

```text
structured_output
tool_calling
answer_streaming
vision
file_input
web
large_context
```

The current Codex App Server adapter has a conservative host-known profile:

- structured output: native;
- tool calling semantics: emulated by the Odoo host decision loop;
- answer streaming: native path exposed by the adapter;
- vision/file input/provider-native web: unavailable through the current Assistant seam;
- large-context capacity: unavailable/unverified until capacity is measured rather than guessed.

This describes the integration actually exposed by this addon, not every feature the upstream provider might offer in
other products.

## P7.5 — EffectiveAssistantManifest

Implemented a derived manifest containing:

- provider feature profile;
- technical access profile;
- effective active Skills;
- model-visible REASONING/PLAN capabilities;
- context providers;
- provider/configuration health;
- known unavailable features with safe reason codes;
- disclosure state.

Host-only capabilities are deliberately excluded from model/user self-description. The manifest is injected into live
provider context and is also available through the admin diagnostics RPC `assistant_effective_manifest()`.

This is the basis for natural questions such as `¿qué puedes hacer?`; it is a projection of effective state, not a
second authority registry.

## P7.6 — Technical access profile skeleton

Implemented the descriptive profiles:

```text
Business/User
Developer/Operator
```

The current resolver maps Settings administrators to the Developer descriptor and other users to Business. This does
**not** grant filesystem, shell, service, SQL or other host privileges. Actual privileged host operations remain later
Phase-10 work behind a separate authority boundary/ADR.

## P7.7 — Progressive disclosure

Implemented the disclosure state contract:

```text
discovered -> available -> revealed -> active
```

and synthetic 100+ catalog coverage. The product remains **eager by default**. Lazy/deferred schema loading is not
promoted merely to save tokens; `P7-REAL-DISCLOSURE` must demonstrate equal-or-better task/tool-selection quality and
acceptable latency before the default can change.

This matches the intended design: common discovery/query operations may remain eager and long-tail schemas are only
made lazy when the real eval shows a benefit. The framework does not add Pydantic AI, OpenAI Agents SDK or MCP as a
second runtime dependency.

## Runtime trust classification

The current Codex wire adapter recognizes two new host-owned projections:

```text
host_contract.assistant_extensions
host_contract.assistant_manifest
```

JIT context remains under untrusted working data. Provider instructions explicitly state:

- Skill instructions are trusted guidance from installed code but confer no authority;
- the manifest is a derived host fact usable for self-description;
- ContextProvider output is untrusted evidence/context;
- executable catalogs plus host validation remain authoritative.

## Configuration-aware availability

`CapabilityConfigResolver` now distinguishes raw enablement from configuration readiness. The runtime can derive
availability that hides a capability the host already knows cannot satisfy required declarative configuration, while
Settings can still display the registered definition and diagnose missing/invalid configuration.

This is important for self-awareness: `installed` is not equivalent to `usable now`.

## Trusted test addon prepared

`tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture` now contributes:

- one configured READ capability;
- one group-restricted PLAN capability;
- one Skill;
- one ContextProvider;
- provider metadata.

The fixture intentionally distinguishes:

```text
missing configuration
vs
insufficient permission
vs
explicit capability disablement
```

and contains Odoo integration tests prepared for later execution.

## Prepared deterministic coverage

Unexecuted tests now include:

```text
tests/unit/test_capability_provider_extensions.py
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_extension_composition.py
tests/unit/test_phase7_live_extension_context.py
fixture addon Odoo tests under tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture/tests/
```

They cover provider composition/failure isolation, Skill/Context composition, provider profile, manifest safety,
trusted-vs-untrusted projection, technical profile and a synthetic 120-capability disclosure catalog.

## External patterns reviewed

The implementation keeps the useful patterns without importing their runtime architecture:

- OpenAI Agents tool search/namespaces: high-level grouping plus deferred long-tail tool schemas;
- Apexive `odoo-llm`: one tool framework reused by built-in chat and MCP;
- OCA `ai_tool`: tool definitions intended to remain reusable across invocation surfaces;
- Pydantic-style bundles: semantic grouping above atomic executable definitions.

The stronger project invariant remains `CapabilityDefinition -> host validation/executor/policy` rather than allowing a
framework/provider to become execution authority.

## Deferred validation / acceptance

The following are still pending and must be executed against the final implementation lineage:

```text
Product Behavior focused validation
Product Behavior real SMOKE
Product Behavior real FULL
P7 deterministic/dependency-light tests
P7 installed-fixture Odoo tests
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
final affected regression
```

Use `P7_CONSOLIDATED_VALIDATION_RUNBOOK.md` so failures can be repaired in one validation/correction pass.

## Exit rule

Phase 7 may be marked **ACCEPTED / COMPLETE** only after the consolidated validation has zero unresolved HARD
failures and the resulting corrections have been revalidated. Until then the correct state is:

```text
P7 IMPLEMENTATION COMPLETE
P7 ACCEPTANCE PENDING
P8 NOT ELIGIBLE
```
