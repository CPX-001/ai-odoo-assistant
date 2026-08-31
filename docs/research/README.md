# Research and execution guidance

This directory contains living implementation playbooks, validation records, product-eval specifications and decision-support material. It is separate from current implementation authority in `docs/`.

## Authority

Research documents do not override:

1. current code on `main` plus accepted ADRs;
2. current documents listed in `docs/README.md`;
3. current deterministic tests and accepted real evidence.

`docs/PRODUCT_VISION.md` defines intended product direction. Playbooks turn that direction into ordered work and gates; unexecuted validation is never PASS.

## Primary execution documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Current cursor, blockers, validation debt and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable multi-run execution and validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named acceptance checks requiring real Odoo/browser/provider paths. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Canonical expensive repository regression when explicitly required. |
| `PRODUCT_BEHAVIOR_EVALS_V1.md` | Permanent user-visible product behavior baseline, metrics and 54 initial scenarios. |
| `PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md` | Current implementation/real-gate handoff, including streaming and one-shot Plan work. |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | P0-P4 foundation path and historical rationale. |
| `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` | P5+ gated product roadmap. |
| `P5.1_TURN_SCOPED_FRONTEND_STATE.md` / `P5.1_VALIDATION_RUNBOOK.md` | Accepted per-conversation frontend-state slice and gates. |
| `P5.2_SCHEDULER_IMPLEMENTATION.md` / `P5.2_VALIDATION_RUNBOOK.md` | Accepted scheduler concurrency/backpressure implementation and gates. |
| `P5.3_STABLE_SETTINGS_SNAPSHOT.md` / `P5.3_VALIDATION_RUNBOOK.md` | Accepted immutable turn settings snapshot and gates. |
| `P5.4_FINAL_ACTIVITY_ANSWER_FAILURE_UX.md` / `P5.4_VALIDATION_RUNBOOK.md` | Accepted final answer/activity/failure UX and gates. |
| `P5.5_POST_EFFECT_REASONING.md` / `P5.5_VALIDATION_RUNBOOK.md` | Accepted verified-receipt post-effect continuation and gates. |
| `P5.6_CONVERSATION_CONTEXT_MANAGER.md` / `P5.6_VALIDATION_RUNBOOK.md` | Accepted ConversationContextManager and gates. |
| `P5.7_MODEL_FAMILY_REASONING_PREFERENCES.md` | Accepted model/reasoning preference work. |
| `P5.7_CONVERSATION_SCOPED_PREFERENCES.md` | Accepted conversation preference mutation work. |
| `P5.8_IMPLEMENTATION.md` / `P5.8_VALIDATION_RUNBOOK.md` | Accepted semantic activity/control/navigation/compensation implementation and historical gate chain. |
| `P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md` | Accepted P6.1/P6.3/P6.5 TaskPlan/EffectPlan/budget foundation. |
| `P6_EFFECT_RECOVERY_JOURNAL_IMPLEMENTATION.md` | Accepted P6.4/P6.6 recovery-unit and EffectJournal implementation. |
| `P6_ADAPTIVE_PLANNING_IMPLEMENTATION.md` | Accepted P6.2 Direct/Plan/replan implementation record. |
| `P7_MINI_FRAMEWORK_IMPLEMENTATION.md` | Current isolated P7.1 provider-extension foundation and live-integration stop boundary. |
| `PHASE3_PUBLIC_ACTIVITY.md` | Formal completed P3 public activity record. |
| `PHASE4_ANSWER_STREAMING.md` | Formal historical P4 answer-streaming acceptance record. |
| `E2E_AGENT_LOOP_CONVERGENCE.md` | Host-loop convergence research behind the current one-decision runtime. |
| `SLICE_TEMPLATE.md` | Historical slice template; current protocol favors the largest coherent feasible product change. |

Supporting phase/evidence records remain here and under `evidence/`.

## Current formal cursor

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 COMPLETE
P7 IN_PROGRESS / LIVE INTEGRATION PAUSED
  P7.1 provider-extension foundation LANDED / focused local validation required
  Product Behavior Evals v1 IMPLEMENTATION + REAL BASELINE REQUIRED
  P7.1 live effective-catalog wiring BLOCKED
  P7.2+ NOT STARTED
P8+ NOT ELIGIBLE
```

`EXECUTION_STATE.md` is authoritative for exact gate IDs and next action.

## Accepted evidence through Phase 6

```text
P5.1 evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md
P5.2 evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md
P5.3 evidence/phase5/2026-08-29/P5.3-REAL-ACCEPTANCE-32e836e.md
P5.4 evidence/phase5/2026-08-29/P5.4-REAL-ACCEPTANCE-3e2b38d.md
P5.5 evidence/phase5/2026-08-29/P5.5-REAL-ACCEPTANCE-8427c88.md
P5.6 evidence/phase5/2026-08-29/P5.6-REAL-ACCEPTANCE-720102f.md
P5.7 model/reasoning evidence/phase5/2026-08-29/P5.7-MODEL-REASONING-ACCEPTANCE-eb66e45.md
P5.7 complete evidence/phase5/2026-08-29/P5.7-REAL-ACCEPTANCE-074a71c.md
P5.8 complete evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
```

P5 and P6 are fully accepted.

## Current P7 boundary

The first Phase-7 implementation foundation now exists but is intentionally isolated from live execution:

```text
CapabilityProvider
CapabilityProviderStatus
Odoo-registry provider discovery
registry composition/provenance
optional-provider failure isolation
provider/capability collision rejection
```

The already-prepared focused test `tests/unit/test_capability_provider_extensions.py` must be executed before any
further P7 code. Even after it passes, live P7 catalog wiring remains paused until the Product Behavior Evals v1 gate
is implemented and accepted.

## Product Behavior Evals v1

The new permanent eval layer exists because deterministic tests can be green while the actual Assistant behaves
poorly. The v1 design separates:

```text
technical deterministic tests
product contract E2E
agentic product evals
```

It defines:

- SMOKE 12–15 scenarios / 1 trial;
- FULL 50+ scenarios / 3 probabilistic trials;
- hard safety/authority/user-contract graders;
- quality scoring for genuinely semantic dimensions;
- normal/limited/admin Odoo personas;
- Spanish/Catalan/English coverage;
- per-provider and per-capability timing;
- real provisional answer-streaming checks;
- Direct vs one-shot Plan UX;
- live-fact grounding, navigation, approvals, batch, Stop/correction and multichat cases.

The first real baseline must have zero unresolved HARD failures before live P7 integration resumes.

## Streaming note

`PHASE4_ANSWER_STREAMING.md` remains historical evidence for the Phase-4 checkpoint. The current user reports a
possible later regression where the UI remains thinking and then displays the complete answer at once. The Phase-6
final periodic regression did not rerun the real first-delta gate, so Product Behavior Evals v1 must re-measure the
current provider delta -> extractor -> Odoo live event -> browser delta path instead of inferring current health from
old evidence.

## Conversation context/cache note

P5.6 provides bounded causal conversation continuity but not a freshness-aware authoritative cache of mutable Odoo
business facts. Repeated-query latency should be measured first. Any later cache that permits skipping a live read
must bind access/company scope, query identity, provenance and freshness/invalidation; the future Evidence layer is
the natural owner unless a smaller Odoo-native optimization is demonstrated.

## Recursive execution rule

Each independent implementation run reconstructs state from Git:

```text
inspect current main
 -> read repository instructions and docs index
 -> read EXECUTION_STATE
 -> process new validation evidence first
 -> repair failed hard gate if any
 -> otherwise select the largest eligible coherent change
 -> inspect current code/ADRs/tests
 -> implement
 -> run focused available validation
 -> execute only broad/real gates explicitly required by current state/runbook
 -> update evidence/state/docs
 -> publish coherent checkpoint
```

Never continue purely from previous chat memory.

## Validation layers

A phase/checkpoint is not complete merely because code exists. Use as applicable:

```text
static/contract review
deterministic executable tests
agentic/product evals
real Odoo/browser/provider acceptance
```

Focused validation is the default during implementation. The repository-wide periodic batch is defined in
`PERIODIC_FULL_REGRESSION_RUNBOOK.md`; the Product Behavior FULL gate is separate and does not automatically authorize
all unrelated repository regressions.

## External implementation references

External Odoo/agent projects are implementation references, not authority replacements. Useful patterns include OCA
`queue_job`, OCA `base_import_async`, OCA `ai_tool`, Odoo AI Server Actions/Agents, Apexive `odoo-llm`, and modern
provider/capability progressive-disclosure/eval patterns.

For borrowed patterns record the concrete problem solved here and the authority/runtime behavior deliberately not
copied.

## No GitHub Actions

Do not use GitHub Actions while repository instructions say no usable runners/workers are available. Required tests
run in an environment that actually provides Odoo/provider/browser dependencies; unrun tests remain pending.

## Research document rules

A playbook/record should:

- start from current code rather than an old report;
- distinguish observed from proposed behavior;
- record inspected baseline/date;
- define implementable coherent work and exit gates;
- identify ADR requirements;
- preserve current authority/recovery invariants;
- avoid premature technology choices when evals can decide them;
- be updated/superseded when newer code invalidates assumptions.
