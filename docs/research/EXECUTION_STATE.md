# Stabilization execution state

State format: 46  
Updated: 2026-08-31

Accepted lineage:

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

P6 is **COMPLETE**. Phase 7 is now active.

## Current cursor

```text
phase: 7
phase_name: mini-framework, feature negotiation and Assistant self-awareness
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P7.1-provider-extension-boundary-foundation
active_slice_record: docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: FOCUSED_DETERMINISTIC_HARD
blocking_work: live effective-catalog integration is intentionally held until the new provider composition boundary passes its focused deterministic gate
blocking_validation: tests/unit/test_capability_provider_extensions.py plus py_compile/ruff for the changed provider/registry boundary
pending_periodic_validation: none; no full regression is authorized by the current slice
periodic_regression_runbook: docs/research/PERIODIC_FULL_REGRESSION_RUNBOOK.md
latest_accepted_evidence: docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
latest_executed_evidence: docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
next_action: run the focused P7.1 provider-extension tests; on PASS continue inside P7.1 by wiring discover_capabilities_for_env(self.env) into all current Odoo-owned effective-catalog surfaces and add installed-provider Odoo coverage
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
  P6.1 TaskPlan vs EffectPlan        VALIDATED_PART1
  P6.2 direct/deliberate/replan      VALIDATED_PART1
  P6.3 multi-step EffectPlan         VALIDATED_PART1
  P6.4 atomic vs segmented effects   VALIDATED_PART2
  P6.5 separate budgets              VALIDATED_PART1
  P6.6 EffectJournal                 VALIDATED_PART2
P7 IN_PROGRESS
  P7.1 CapabilityProvider API        LOCAL_VALIDATION_REQUIRED
  P7.2 Skill/Bundle                  NOT_STARTED
  P7.3 ContextProvider               NOT_STARTED
  P7.4 ProviderProfile               NOT_STARTED
  P7.5 EffectiveAssistantManifest    NOT_STARTED
  P7.6 Technical profile skeleton    NOT_STARTED
  P7.7 Progressive disclosure        NOT_STARTED
P8+ NOT_ELIGIBLE
```

## Phase-6 acceptance checkpoint

The final current-product regression published by `0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0`
closed Phase 6. Its accepted evidence is:

```text
docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
```

It passed the complete current dependency-light/static, Odoo addon and HOOT suites plus all six
Phase-6 real gates. There is no remaining Phase-6 gate blocking P7.

## Current P7.1 implementation candidate

Starting from accepted `0b1bcab`, Phase 7 now has the provider-extension foundation described in:

```text
docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md
```

Current code adds:

```text
CapabilityProvider
CapabilityProviderStatus
discover_odoo_capability_providers(env)
compose_capability_registry(...)
discover_capabilities_for_env(env)
provider provenance on CapabilityRegistry/catalog
optional-provider failure isolation
provider/capability identity conflict rejection
```

The Odoo-registry marker is `_odoo_ai_capability_provider` on trusted installed model code. Discovery
is constrained to the active Odoo registry; it does not scan arbitrary host packages/filesystem.

This foundation deliberately does **not** yet alter live turn execution. That is the next step of the
same P7.1 slice after focused deterministic acceptance. This boundary prevents third-party provider
composition from entering the authoritative runtime before its duplicate/failure-isolation contract
has executed successfully.

Focused test prepared:

```text
tests/unit/test_capability_provider_extensions.py
```

No test in that file has been recorded PASS yet.

## Phase-7 target order

The active playbook remains authoritative for the target:

```text
P7.1 CapabilityProvider API
P7.2 Skill/Bundle
P7.3 ContextProvider
P7.4 ProviderProfile feature negotiation
P7.5 EffectiveAssistantManifest / self-awareness
P7.6 Business vs Developer/Operator technical profile skeleton
P7.7 progressive disclosure when catalog/evals justify it
```

Do not start P7.2 while P7.1's authority-relevant effective catalog boundary is still unvalidated.

## Phase-7 real gates — all pending

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

None is PASS merely because the contract or test fixture exists.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- `CapabilityProvider` contributes trusted declarations; it does not own execution authorization.
- Planning strategy and TaskPlan never grant effect authority.
- Direct mode does not weaken EffectPlan/policy/approval/verification.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- Policy/approval/preconditions/write-barrier/verification remain host-owned.
- Recovery-unit mode/classification is host-derived.
- Persisted in-flight effects are never blindly retried.
- Stop/redirect cannot bypass the effect boundary.
- Raw/private provider reasoning never becomes TaskPlan/activity/journal content.
- Provider-specific reasoning adapters remain below neutral host contracts.
- Optional extension failures must not remove the valid core capability catalog.
- Duplicate capability/provider identity must fail closed rather than shadow existing authority.
- Broad/real validation is batched only when the authoritative slice/runbook requires it.
- No GitHub Actions are used while repository policy says usable runners are unavailable.

## Exact stop rule

Execute the focused P7.1 provider-extension deterministic gate before wiring external providers into
the live Odoo turn catalog. If it passes, continue inside the same P7.1 slice. If it fails, repair P7.1
before any P7.2 work. Do not run a full regression for this checkpoint unless a concrete failure expands
the blast radius or the authoritative state/runbook is updated to require one.
