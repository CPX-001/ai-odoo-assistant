# Research and execution guidance

This directory contains living implementation playbooks, validation records and decision-support material. It is separate from current implementation authority in `docs/`.

## Authority

Research documents do not override:

1. current code on `main` plus accepted ADRs;
2. current documents listed in `docs/README.md`;
3. current deterministic tests.

`docs/PRODUCT_VISION.md` defines intended product direction. The playbooks here turn that direction into ordered slices and gates; they do not claim future behavior is implemented.

## Primary execution documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Current cursor, blockers, validation debt and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable multi-run execution and validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named acceptance checks requiring the real Odoo/browser/provider path. |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | P0-P4 foundation path and historical rationale; newer phase records/current code supersede stale future-state wording inside it. |
| `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` | P5+ gated product roadmap: non-blocking multi-chat, planning/effects, mini-framework, Evidence/RAG, technical operations, imports, multimodal, extra surfaces and providers. |
| `P5.1_TURN_SCOPED_FRONTEND_STATE.md` | Completed P5.1 implementation/validation record for per-conversation frontend execution ownership. |
| `P5.1_VALIDATION_RUNBOOK.md` | Executable P5.1 handoff for HOOT/regression plus real multi-chat, settings-snapshot and reopen browser checks. |
| `P5.2_SCHEDULER_PREPARATION.md` | Historical design preparation that identified the P5.2 capacity/causality/fairness/wake-up gaps before implementation. |
| `P5.2A_SCHEDULER_CAPACITY_CAUSALITY.md` | P5.2a implementation record for bounded capacity and causal claim eligibility. |
| `P5.2_SCHEDULER_IMPLEMENTATION.md` | Current full P5.2 implementation record: capacity, ordering, fairness, wake-up, diagnostics and real-gate harness. |
| `P5.2_VALIDATION_RUNBOOK.md` | Batched deterministic/regression/real-environment acceptance procedure for the complete P5.2 implementation. |
| `P5.3_STABLE_SETTINGS_SNAPSHOT.md` | Current P5.3 implementation record for the versioned immutable per-turn settings snapshot. |
| `P5.3_VALIDATION_RUNBOOK.md` | Split P5.3 validation sequence; current stop is the focused Odoo snapshot gate. |
| `PHASE3_PUBLIC_ACTIVITY.md` | Formal completed status record for P3 public activity. |
| `PHASE4_ANSWER_STREAMING.md` | Formal completed status record for P4 answer streaming. |
| `E2E_AGENT_LOOP_CONVERGENCE.md` | Host-loop convergence research behind the current one-decision runtime. |
| `SLICE_TEMPLATE.md` | Atomic implementation slice template. |
| `PHASE23_REAL_VALIDATION_RUNBOOK.md` | Reproducible P2/P3 validation procedure. |
| `PHASE34_REAL_VALIDATION_RUNBOOK.md` | Reproducible P3/P4 validation procedure for landed code. |

Supporting phase/evidence records remain in this directory and under `evidence/`.

`PHASE3_PUBLIC_ACTIVITY_PREPARATION.md` is now a historical preparation record; use `PHASE3_PUBLIC_ACTIVITY.md` for current P3 status. `P5.2_SCHEDULER_PREPARATION.md` is likewise historical preparation; current P5.2 behavior is documented in `P5.2_SCHEDULER_IMPLEMENTATION.md`.

## Current formal cursor

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 IN_PROGRESS; P5.1 and P5.2 complete, P5.3 LOCAL_VALIDATION_REQUIRED
P6+ not eligible
```

`EXECUTION_STATE.md` is authoritative for exact gate IDs.

The ordered P2 -> P3 -> P4 gates passed on 2026-08-28. The sanitized record is
`evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`.

P5.1 passed its recorded HOOT/P2-P4 regression and focused real browser gates on 2026-08-28. The
sanitized record is `evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md`.

P5.2 scheduler concurrency/backpressure is implemented and accepted across its intended internal
a/b/c scope, including bounded capacity, causal ordering, anti-starvation fairness, capacity-release
wake-up, aggregate diagnostics and the real browser gates. The accepted batch is recorded in
`evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`.

P5.3 now has a versioned host-owned turn settings snapshot, focused Odoo coverage and addon version
checkpoint. No P5.3 validation is claimed PASS yet. The next mandatory gate is
`P5.3-ODOO-SETTINGS-SNAPSHOT`, after which regression and real settings-snapshot validation can be
run as a separate slice. P5.4 remains blocked until the focused P5.3 contract passes.

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

A phase/slice is not complete merely because code exists.

Use as applicable:

```text
static/contract review
deterministic executable tests
agentic/product evals
real Odoo/browser/provider acceptance
```

Hard gates block dependent contracts. Soft debt is allowed only when explicitly classified by the execution protocol.

## External implementation references

External Odoo projects are implementation references, not authority replacements:

- OCA `queue_job`: configurable channels/capacity, parallel background jobs and stale-job recovery;
- OCA `base_import_async`: large imports moved to background processing;
- OCA `ai_tool`: reusable AI tool concepts across native/MCP-style surfaces;
- Odoo AI Server Actions: manager/tool separation;
- Apexive `odoo-llm`: providers, decorator-based tools, Knowledge/RAG/citations, domain tools and MCP breadth;
- OpenAI Agents/Pydantic-style namespaces/capability loading: progressive disclosure patterns.

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
