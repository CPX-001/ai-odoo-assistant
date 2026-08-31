# Stabilization execution state

State format: 50  
Updated: 2026-08-31

## Accepted lineage

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 through 688f569d441a40a4637ad6a23f111e584e18c955
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
```

P6 is **COMPLETE**. No Phase-7 implementation after the accepted P6 checkpoint is promoted or accepted by this
record unless explicit validation evidence says so.

## User-directed validation sequencing override

On 2026-08-31 the user explicitly requested that implementation continue and that the pending gates be accumulated
for validation later. This changes the **sequencing stop rule**, not the acceptance criteria:

```text
implementation may continue across P7 slices
validation gates remain pending
no deferred gate may be reported as PASS
P7 remains IN_PROGRESS until the accumulated gates are actually executed and accepted
```

The Product Behavior Evals v1 gate is therefore no longer a code-sequencing blocker for this session, but it remains
a required promotion gate together with the Phase-7 deterministic/real gates.

## Current cursor

```text
phase: 7
phase_name: mini-framework, feature negotiation and Assistant self-awareness
phase_state: IN_PROGRESS_IMPLEMENTATION_ADVANCING_VALIDATION_DEFERRED
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice_record: docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md
current_gate_type: DEFERRED_ACCUMULATED_VALIDATION
blocking_work: none from the deferred validation gates; continue only changes coherent with current P7 architecture
blocking_validation: none for implementation sequencing by explicit user direction; all listed gates remain required before P7 acceptance
latest_accepted_evidence: docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
latest_executed_evidence: docs/research/evidence/phase7/2026-08-31/P7.1-FOUNDATION-3c9e118.md
unvalidated_p7_code_checkpoint: 75e4a2c74b29c7309bfc7688f182466901659c58
next_action: continue P7.2/P7.3 live Skill/Context activation and P7.4/P7.5 provider-profile/manifest binding, then prepare the installed test-provider fixture; do not mark the phase accepted
```

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 COMPLETE
P7 IN_PROGRESS / VALIDATION DEFERRED
  PRE-P7 Product Behavior Evals v1   IMPLEMENTED / VALIDATION_PENDING
  P7.1 CapabilityProvider API        LIVE_WIRING_IMPLEMENTED / VALIDATION_PENDING
  P7.2 Skill/Bundle                  CONTRACT+COMPOSITION_IMPLEMENTED / LIVE_ACTIVATION_PENDING
  P7.3 ContextProvider               CONTRACT+COMPOSITION_IMPLEMENTED / LIVE_ACTIVATION_PENDING
  P7.4 ProviderProfile               CONTRACT_IMPLEMENTED / CURRENT_PROVIDER_BINDING_PENDING
  P7.5 EffectiveAssistantManifest    CONTRACT+DERIVATION_IMPLEMENTED / PRODUCT_BINDING_PENDING
  P7.6 Technical profile skeleton    IMPLEMENTED / NO_PRIVILEGED_AUTHORITY
  P7.7 Progressive disclosure        CONTRACT_IMPLEMENTED / DEFAULT_DISABLED / EVAL_GATED
P8+ NOT_ELIGIBLE_FOR_ACCEPTANCE
```

## P7 implementation now present on main

### P7.1 — installed-addon capability providers

The previously isolated provider foundation is now wired into the current Odoo-owned effective-catalog surfaces:

```text
live embedded host loop -> discover_capabilities_for_env(self.env)
settings/catalog/config -> discover_capabilities_for_env(self.env)
reversion/compensation -> discover_capabilities_for_env(self.env)
reversion eligibility -> discover_capabilities_for_env(self.env)
```

This means trusted installed Odoo addons can contribute `CapabilityDefinition` objects through the registry marker
`_odoo_ai_capability_provider` while the existing executor/policy/ACL/approval/verification boundary remains the only
execution authority. Optional provider failures and identity conflicts remain fail-isolated/fail-closed according to
the provider contract.

### P7.2/P7.3 — Skill and Context resource layer

The framework now contains:

```text
SkillDefinition / SkillCatalog
ContextProvider / ContextProviderCatalog
CapabilityProvider.skills
CapabilityProvider.context_providers
AssistantExtensionCatalog
ActiveAssistantExtensions
```

Skills carry behavior/instructions/selectors/config/eval ownership but no authorization. Context providers return
bounded JSON data and are explicitly treated as data, not policy. Non-executable resources are composed only for a
provider whose executable capability provider was accepted by the host registry; optional resource collisions are
isolated without shadowing existing identities.

`AssistantExtensionCatalog.activate(...)` resolves host-enabled Skills and only the JIT ContextProviders selected by
those Skills. The contract exists, but the active Skill instructions/JIT context are **not yet injected into the live
Codex decision input** at this checkpoint.

### P7.4/P7.5/P7.6/P7.7 contract layer

Current framework code also contains:

```text
ProviderProfile
ProviderFeature / ProviderFeatureState(native|emulated|unavailable)
EffectiveAssistantManifest
TechnicalAccessProfile(BUSINESS|DEVELOPER)
DisclosurePolicy
CapabilityDisclosureSnapshot
```

The manifest is a derived projection, not a second authority registry. It omits handlers and Skill instructions from
browser payloads. Progressive disclosure is deliberately disabled by default until catalog-scale/product evals justify
hiding detailed schemas. The current Codex adapter has not yet been bound to a product-level `ProviderProfile`, so no
feature-support claims should be surfaced to users yet.

## Validation accumulated for later

### Product Behavior Evals v1

The current Product Behavior implementation remains unaccepted until its focused/static/Odoo/HOOT checks and real
SMOKE/FULL runs are executed. Owning documents:

```text
docs/research/PRODUCT_BEHAVIOR_EVALS_V1.md
docs/research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md
docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md
```

The gate still includes one-shot Plan behavior, real answer streaming, ACL/persona behavior, provider/capability
timing, grounding and zero unresolved HARD failures.

### Phase-7 deterministic/eval gate

Still required before Phase-7 acceptance:

```text
trusted installed test addon contributes:
  one Skill
  one READ capability
  one PLAN capability
  one ContextProvider
  configuration

validate:
  enable/disable/uninstall
  missing configuration vs permission denial
  self-description accuracy
  explicit hidden-capability call denied
  synthetic 100+ capability catalog with/without disclosure
  optional-provider/resource failure isolation
  provider identity/capability/resource collision behavior
```

New dependency-light tests have been added for the P7 negotiation/resource contracts, but they have **not been run**
after the latest implementation changes in this record.

### Phase-7 real gates — all pending

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

None is claimed by this state record.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute under the effective user with `su=False`.
- `CapabilityDefinition` remains the atomic executable authority.
- Provider/Skill/Context metadata cannot grant ACL, policy, approval or write authority.
- Duplicate extension identities never silently shadow existing definitions/resources.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- Policy, approval, preconditions, write barrier, verification and recovery remain host-owned.
- Context/source/record/log text is data and cannot redefine system/tool policy.
- Raw/private provider reasoning never becomes product progress, eval evidence or public diagnostics.
- Progressive disclosure cannot hide an executable capability from host-side validation; it only changes what is revealed to the model.

## Validation policy for the current session

Continue implementing coherent Phase-7 code while the user owns the later validation pass. Keep an explicit list of
pending gates. If a change requires evidence to choose between incompatible architectures rather than merely to
promote/accept code, stop at that design uncertainty rather than inventing an answer.
