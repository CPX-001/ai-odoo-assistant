# Research and execution guidance

This directory contains living implementation playbooks, validation records and decision-support material. It is separate from current implementation authority in `docs/`.

## Authority

Research documents do not override:

1. current code on `main` plus accepted ADRs;
2. current documents listed in `docs/README.md`;
3. current deterministic tests.

`docs/PRODUCT_VISION.md` defines intended product direction. Playbooks turn that direction into ordered work and gates; unexecuted validation is never PASS.

## Primary execution documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Current cursor, blockers, validation debt and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable multi-run execution and validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named acceptance checks requiring real Odoo/browser/provider paths. |
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
| `P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md` | Current P6.1/P6.3/P6.5 implementation candidate and validation boundary. |
| `PHASE3_PUBLIC_ACTIVITY.md` | Formal completed P3 public activity record. |
| `PHASE4_ANSWER_STREAMING.md` | Formal completed P4 answer streaming record. |
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
P6 IN_PROGRESS
  P6.1 IMPLEMENTED_CANDIDATE
  P6.2 NOT_STARTED
  P6.3 IMPLEMENTED_CANDIDATE
  P6.4 NOT_STARTED
  P6.5 FOUNDATION_IMPLEMENTED_CANDIDATE
  P6.6 NOT_STARTED
P7+ NOT_ELIGIBLE
```

`EXECUTION_STATE.md` is authoritative for exact gate IDs and next action.

## Accepted Phase-5 evidence

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
```

P5.8 is fully accepted. Earlier text saying it still required real validation is obsolete.

## Current Phase-6 candidate

The current large checkpoint intentionally groups the tightly related foundation for:

```text
P6.1 TaskPlan vs EffectPlan
P6.3 bounded multi-step EffectPlan
P6.5 separate budget families
```

The implementation is provider-neutral at the host boundary. Codex is the current concrete adapter because it is the configured provider, but TaskPlan/EffectPlan/budget/authority semantics do not live in Codex code.

The candidate must now be validated as one coherent checkpoint before P6.4/P6.6. No P6 real gate is PASS merely because code/tests exist.

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
 -> run available validation
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

Hard gates block dependent contracts. Soft debt is allowed only when explicitly classified by the execution protocol.

## External implementation references

External Odoo/agent projects are implementation references, not authority replacements. Useful patterns include OCA `queue_job`, OCA `base_import_async`, OCA `ai_tool`, Odoo AI Server Actions, Apexive `odoo-llm`, and provider/capability progressive-disclosure patterns from modern agent frameworks.

For borrowed patterns record the concrete problem solved here and the authority/runtime behavior deliberately not copied.

## No GitHub Actions

Do not use GitHub Actions while repository instructions say no usable runners/workers are available. Required tests run in an environment that actually provides Odoo/provider/browser dependencies; unrun tests remain pending.

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
