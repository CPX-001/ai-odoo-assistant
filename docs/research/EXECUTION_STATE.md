# Stabilization execution state

State format: 54
Updated: 2026-09-01

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

P0-P6 remain accepted. Phase-7 code after the P6 checkpoint is **not accepted yet** unless the consolidated validation
below is actually executed and recorded.

## User-directed validation sequencing

On 2026-08-31 the user requested that Phase-7 implementation be finished first and that the pending tests plus
corrections be executed afterward as one consolidated pass. That sequencing choice has now been applied.

It changes implementation order only:

```text
implementation may be complete
validation may still be pending
unexecuted gates are never PASS
P8 stays blocked until P7 acceptance
```

## Current cursor

```text
phase: 7
phase_name: mini-framework, feature negotiation and Assistant self-awareness
phase_state: IMPLEMENTATION_COMPLETE_ACCEPTANCE_BLOCKED_PROVIDER_CAPACITY
active_phase_record: docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md
active_validation_runbook: docs/research/P7_CONSOLIDATED_VALIDATION_RUNBOOK.md
current_gate_type: CONSOLIDATED_P7_AND_PRODUCT_VALIDATION
blocking_work: no planned Phase-7 implementation slice remains before validation
blocking_validation: Product Behavior FULL x3 stopped at 76/162 PASS by current provider usage limit; then final periodic regression
latest_accepted_evidence: docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
latest_executed_p7_evidence: docs/research/evidence/phase7/2026-09-01/P7-CONSOLIDATED-2992214.md
latest_executed_product_evidence: docs/research/evidence/product_behavior/2026-09-01/PRODUCT-BEHAVIOR-BASELINE-e100dba.md
next_action: after current provider quota returns, rerun Product Behavior FULL x3 from the beginning; if green run the final periodic regression and publish P7 acceptance
```

## Chat workflow/activity repair checkpoint — 2026-09-01

Evidence: `docs/research/CHAT_WORKFLOW_ACTIVITY_REPAIR_20260901.md`.

This post-checkpoint repair adds a bounded transactional related-record creation workflow, guarantees an approved
turn another queue claim, excludes terminal turns from active-turn restoration, and persists settled public activity
with each Assistant message. Focused Odoo and HOOT validation is green; no real provider request was made against the
user's changed Codex account. This repair does not change the P7 acceptance cursor or convert the blocked FULL x3 gate
into PASS.

## Phase-7 consolidated validation checkpoint — 2026-09-01

Evidence: `docs/research/evidence/phase7/2026-09-01/P7-CONSOLIDATED-2992214.md`.

```text
P7 deterministic/static                         PASS (26 pytest; Ruff/compile/diff-check)
Product Behavior focused                       PASS (53 pytest)
focused Odoo settings                          PASS (5 methods / 7 counted)
installed fixture Odoo                         PASS (5 methods / 7 counted)
clean core install                             PASS
focused HOOT                                   PASS (10 tests / 32 assertions)
Product Behavior real SMOKE                    PASS (15/15; min/mean quality 100)
P7-REAL-PROVIDER-DISCOVERY                     PASS
P7-REAL-SELF-AWARENESS                         PASS
P7-REAL-DISABLEMENT                            PASS
P7-REAL-CONTEXT-PROVIDER                       PASS
P7-REAL-DISCLOSURE                             PASS
P7-REAL-AUTHORITY                              PASS
Product Behavior FULL x3                       BLOCKED (76/162 PASS; 0 HARD failures)
final periodic regression                      NOT EXECUTED (FULL prerequisite blocked)
```

Repairs during the pass fixed real Odoo synthesized-class provider discovery, fail-open required-group
availability, and unnecessary clarification for omitted optional contact fields. P8 remains ineligible
until a complete FULL x3 and the subsequent final regression are green. Do not combine the partial 76
trials with a later partial run, use the old Codex session, or consume a usage reset without explicit
authorization.

## Product Behavior checkpoint — 2026-09-01

The v1 real disposable-Odoo runner and diagnosed product repairs were exercised before the concurrent Phase-7
implementation commits reached `main`. The checkpoint was then rebased onto `c8756b2` without reverting the newer
P7 architecture. Evidence is in
`docs/research/evidence/product_behavior/2026-09-01/PRODUCT-BEHAVIOR-BASELINE-e100dba.md`.

```text
focused deterministic/static on rebased candidate       PASS (53 pytest)
focused Odoo on rebased candidate                       PASS (25 methods / 31 counted)
navigation Odoo repeat                                  PASS (11 methods / 13 counted)
canonical addon HOOT on rebased candidate               PASS (161 tests / 618 assertions)
real SMOKE on pre-P7-integration candidate              PASS (15/15, one trial)
initial real FULL diagnostic                            FAIL baseline (41/54 before repairs)
post-repair focused real scenarios                      PASS (9/9 executed)
post-repair PB-ACT-010                                  BLOCKED provider usageLimitExceeded
current-candidate real SMOKE and FULL x3                BLOCKED provider capacity
```

Do not use the previous Codex account/session to bypass this blocker and do not consume a usage reset without user
authorization. No scenario is marked PASS without execution. P7 remains implemented but unaccepted; P8 stays
blocked.

## Phase summary

```text
P0 COMPLETE / ACCEPTED
P1 COMPLETE / ACCEPTED
P2 COMPLETE / ACCEPTED
P3 COMPLETE / ACCEPTED
P4 COMPLETE / ACCEPTED
P5 COMPLETE / ACCEPTED
P6 COMPLETE / ACCEPTED
P7 IMPLEMENTATION COMPLETE / ACCEPTANCE PENDING
  PRE-P7 Product Behavior Evals v1   IMPLEMENTED / PARTIAL_VALIDATION_BLOCKED_PROVIDER_CAPACITY
  P7.1 CapabilityProvider API        IMPLEMENTED_LIVE / VALIDATION_PENDING
  P7.2 Skill/Bundle                  IMPLEMENTED_LIVE / VALIDATION_PENDING
  P7.3 ContextProvider               IMPLEMENTED_LIVE / VALIDATION_PENDING
  P7.4 ProviderProfile               IMPLEMENTED_BOUND / VALIDATION_PENDING
  P7.5 EffectiveAssistantManifest    IMPLEMENTED_LIVE / VALIDATION_PENDING
  P7.6 Technical profile skeleton    IMPLEMENTED / NO_PRIVILEGED_AUTHORITY
  P7.7 Progressive disclosure        FRAMEWORK_IMPLEMENTED / EAGER_DEFAULT / PROMOTION_EVAL_GATED
P8+ NOT_ELIGIBLE
```

## Phase-7 implementation now present

### Effective provider extension boundary

Trusted installed Odoo addons can contribute `CapabilityProvider` markers through the active Odoo registry. Their
`CapabilityDefinition` objects compose into the same effective registry used by:

```text
live host loop
Settings / capability diagnostics
plan/reversion/compensation paths
```

Provider/capability/executor collisions fail closed. Optional provider failure cannot remove the core catalog.

### Skills and JIT context

`CapabilityProvider` may now contribute `SkillDefinition` and `ContextProvider` resources. The live decision path:

```text
effective registry
 -> AssistantExtensionCatalog
 -> active Skills
 -> selected bounded ContextProviders
 -> AssistantExtensionDecisionEngine
 -> provider adapter
```

Trust separation is explicit:

```text
Skill instructions       trusted installed-code guidance, NO authority
Assistant manifest       host-derived projection, NO authority
ContextProvider payload  untrusted contextual data
CapabilityDefinition     executable unit still validated by host
```

### Provider feature negotiation

`ProviderProfile` records `native | emulated | unavailable` for structured output, tool calling, answer streaming,
vision, file input, web and large context. The current Codex App Server binding is intentionally conservative and
describes only features exposed through this addon.

### Effective self-awareness

`EffectiveAssistantManifest` is derived from the current provider profile, effective REASONING/PLAN catalog, Skills,
ContextProviders, technical profile and sanitized configuration/provider health. Host-only capabilities are excluded.

The manifest is available to live reasoning and through admin diagnostics (`assistant_effective_manifest()`). It is a
projection, not a second tool/authority registry.

### Technical profile

`Business/User` vs `Developer/Operator` is descriptive only in Phase 7. It grants no shell/filesystem/SQL/service or
other host privilege. Those remain Phase-10 work behind a dedicated privilege boundary.

### Progressive disclosure

The framework implements `discovered -> available -> revealed -> active` state and synthetic 100+ catalog coverage,
but the current product remains eager by default. Lazy disclosure cannot be promoted simply for token savings; the
real disclosure gate must preserve task/tool-selection quality and acceptable latency.

This is consistent with the project's progressive-disclosure rule: activation is an eval decision, not a reason to
introduce a second agent/runtime framework.

## Prepared Phase-7 fixture/tests

The trusted fixture addon is:

```text
tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture
```

It contains a configured READ capability, a Settings-admin-only PLAN capability, a Skill, a ContextProvider and Odoo
integration tests. It distinguishes missing configuration, permission denial and explicit capability disablement.

Dependency-light tests prepared for the final pass:

```text
tests/unit/test_capability_provider_extensions.py
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_extension_composition.py
tests/unit/test_phase7_live_extension_context.py
```

None of the newly added/deferred tests is reported PASS by this state record.

## Required consolidated validation

Follow `docs/research/P7_CONSOLIDATED_VALIDATION_RUNBOOK.md` in order:

```text
1. P7 dependency-light + static
2. Product Behavior focused gate
3. installed-fixture Odoo gate
4. Product Behavior real SMOKE
5. P7-REAL-PROVIDER-DISCOVERY
6. P7-REAL-SELF-AWARENESS
7. P7-REAL-DISABLEMENT
8. P7-REAL-CONTEXT-PROVIDER
9. P7-REAL-DISCLOSURE
10. P7-REAL-AUTHORITY
11. Product Behavior FULL
12. final affected/full regression required by the periodic runbook
```

A HARD failure freezes acceptance, is repaired at the owning layer, and is rerun before downstream acceptance.

## Product Behavior gate retained

The permanent Product Behavior v1 layer remains required. Its 54-case dataset, SMOKE/FULL policy, one-shot Plan
behavior, answer-streaming validation, timing, persona/ACL coverage and hard product invariants were intentionally not
removed just because implementation continued.

Historical Phase-4 streaming PASS remains historical only; the current real first-delta path must be measured again.

## Authority invariants carried forward

- Odoo remains persistence and operational authority.
- Business execution uses the effective user with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills/manifests/context/provider metadata cannot create execution authority.
- Hidden/disabled/unauthorized capabilities cannot be made executable by naming them in a prompt.
- Planning strategy/TaskPlan do not grant effect authority.
- Effects remain preview/policy/approval/barrier/execute/verify host-owned operations.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- Raw/private provider reasoning never becomes public activity, TaskPlan, manifest or eval evidence.
- Provider-specific behavior stays beneath the neutral `NextDecisionEngine` contract.
- No unexecuted validation may be represented as acceptance evidence.

## Exit rule

Phase 7 becomes accepted only after the consolidated pass has zero unresolved HARD failures and all repairs have been
revalidated. Then update this cursor to:

```text
P7 COMPLETE / ACCEPTED
P8 ELIGIBLE
```

Until that evidence exists, the authoritative state is:

```text
P7 IMPLEMENTATION COMPLETE / ACCEPTANCE PENDING
P8 NOT ELIGIBLE
```
