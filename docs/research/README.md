# Research and execution guidance

This directory contains living implementation playbooks, validation records and decision-support material. It is separate from current implementation authority in `docs/`.

## Authority

Research documents do not override:

1. current code on `main` plus accepted ADRs;
2. current documents listed in `docs/README.md`;
3. current deterministic tests.

`docs/PRODUCT_VISION.md` defines intended product direction. The playbooks here turn that direction into ordered slices and gates; they do not turn unexecuted validation into PASS.

## Primary execution documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Current cursor, blockers, validation debt and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable multi-run execution and validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named acceptance checks requiring the real Odoo/browser/provider path. |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | P0-P4 foundation path and historical rationale. |
| `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` | P5+ gated product roadmap. |
| `P5.1_TURN_SCOPED_FRONTEND_STATE.md` / `P5.1_VALIDATION_RUNBOOK.md` | Accepted per-conversation frontend-state slice and gates. |
| `P5.2_SCHEDULER_IMPLEMENTATION.md` / `P5.2_VALIDATION_RUNBOOK.md` | Accepted scheduler concurrency/backpressure implementation and gates. |
| `P5.3_STABLE_SETTINGS_SNAPSHOT.md` / `P5.3_VALIDATION_RUNBOOK.md` | Accepted immutable turn settings snapshot and gates. |
| `P5.4_FINAL_ACTIVITY_ANSWER_FAILURE_UX.md` / `P5.4_VALIDATION_RUNBOOK.md` | Accepted final answer/activity/failure UX and gates. |
| `P5.5_POST_EFFECT_REASONING.md` / `P5.5_VALIDATION_RUNBOOK.md` | Accepted verified-receipt post-effect continuation and gates. |
| `P5.6_CONVERSATION_CONTEXT_MANAGER.md` / `P5.6_VALIDATION_RUNBOOK.md` | Accepted ConversationContextManager and gates. |
| `P5.7_MODEL_FAMILY_REASONING_PREFERENCES.md` | Accepted model-family/model-variant/reasoning-effort sub-slice. |
| `P5.7_CONVERSATION_SCOPED_PREFERENCES.md` | Accepted conversation autonomy/response-language mutation slice. |
| `P5.8_SEMANTIC_ACTIVITY_UX.md` | Pre-implementation P5.8 target/product specification. |
| `P5.8_IMPLEMENTATION.md` | Current P5.8 implementation record and deliberate architecture simplifications. |
| `P5.8_VALIDATION_RUNBOOK.md` | Required local/Odoo/HOOT/real gate chain before P5.8 acceptance. |
| `PHASE3_PUBLIC_ACTIVITY.md` | Formal completed P3 public activity record. |
| `PHASE4_ANSWER_STREAMING.md` | Formal completed P4 answer streaming record. |
| `E2E_AGENT_LOOP_CONVERGENCE.md` | Host-loop convergence research behind the current one-decision runtime. |
| `SLICE_TEMPLATE.md` | Atomic implementation slice template. |

Supporting phase/evidence records remain in this directory and under `evidence/`.

## Current formal cursor

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 IN_PROGRESS
  P5.1 COMPLETE
  P5.2 COMPLETE
  P5.3 COMPLETE
  P5.4 COMPLETE
  P5.5 COMPLETE
  P5.6 COMPLETE
  P5.7 COMPLETE
  P5.8 REAL_ENV_VALIDATION_REQUIRED
P6+ NOT ELIGIBLE
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
```

P5.8 code and tests are present, but no P5.8 validation result is recorded by the implementation-only run. Repository instructions prohibit substituting GitHub Actions for the disposable Odoo/Codex/Chromium environment, so unexecuted P5.8 gates remain pending.

The P5.8 implementation adds host-owned lifecycle correlation, semantic reducer/presentation profiles, bounded readable reasoning summaries with raw-reasoning rejection, typed Odoo record/model references with fresh ACL revalidation, generic current-schema record presentation and bounded progressive disclosure. See `P5.8_IMPLEMENTATION.md` for exact current behavior and `P5.8_VALIDATION_RUNBOOK.md` for the acceptance chain.

## Recursive execution rule

Each independent implementation run reconstructs state from Git:

```text
inspect current main
 -> read repository instructions and docs index
 -> read EXECUTION_STATE
 -> process new validation evidence first
 -> repair failed hard gate if any
 -> otherwise select one eligible coherent slice
 -> inspect current code/ADRs/tests
 -> implement
 -> run only available validation
 -> update evidence/state/docs
 -> publish coherent checkpoint
```

Never continue purely from previous chat memory.

## Validation layers

A phase/slice is not complete merely because code exists. Use as applicable:

```text
static/contract review
deterministic executable tests
agentic/product evals
real Odoo/browser/provider acceptance
```

Hard gates block dependent contracts. Soft debt is allowed only when explicitly classified by the execution protocol.

## External implementation references

External Odoo projects are implementation references, not authority replacements. Relevant proven patterns include OCA `queue_job`, OCA `base_import_async`, OCA `ai_tool`, Odoo AI Server Actions, Apexive `odoo-llm`, and provider/capability progressive-disclosure patterns from modern agent frameworks.

For every borrowed pattern record what concrete problem it solves here and what authority/runtime behavior is deliberately not copied.

## No GitHub Actions

Do not use GitHub Actions for this roadmap while repository instructions say no usable runners/workers are available. Required tests run in an environment that actually provides the needed Odoo/provider/browser dependencies; unrun tests remain pending.

## Research document rules

A playbook should:

- start from current code rather than an old report;
- distinguish observed from proposed behavior;
- record inspected baseline/date;
- define implementable slices and exit gates;
- identify ADR requirements;
- preserve current authority/recovery invariants;
- avoid premature technology choices when evals can decide them;
- be updated/superseded when newer code invalidates assumptions.
