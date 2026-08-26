# Stabilization execution state

State format: 1  
Updated: 2026-08-26  
Product/code baseline inspected: `b6a7b77bc91b7e80b25551d0c07334d396f68083`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0-LIVE-BASELINE
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
next_phase: 1
```

## Current fact pattern

Phase 0 implementation tooling is already present and documented in `PHASE0_BASELINE.md`:

- machine-readable scenario matrix;
- browser/provider timing instrumentation;
- redacted live Odoo HTTP capture runner;
- one-trace summarizer;
- aggregate Phase 0 gate evaluator.

The remaining Phase 0 exit gate depends on real Odoo 18 + authenticated/configured Codex evidence. Repository-only work must not pretend this evidence exists.

## Active slice — P0-LIVE-BASELINE

Objective: collect enough real-environment evidence for `phase0_report.py` to decide whether Phase 1 may start.

Prerequisites: implemented.

Implementation state: no speculative provider refactor is currently authorized.

Required real validations:

- [ ] `P0-REAL-HELLO`
- [ ] `P0-REAL-READ`
- [ ] `P0-REAL-ACTION`
- [ ] at least five distinct `P0-REAL-FAILURE-PAIR-*` paths

Required evidence/gate:

- [ ] hello/read/action/failure live captures exist;
- [ ] one successful live turn decomposes queue/provider/tool/finalization latency;
- [ ] simple-turn latency is attributable from measurements;
- [ ] five distinct original-error vs UI-error pairs are recorded;
- [ ] `tests/e2e/phase0_report.py` returns `ready_for_phase1=true` on the collected evidence.

Reference procedure: `REAL_ENV_VALIDATION_PROTOCOL.md` and `PHASE0_BASELINE.md`.

## Exact next action

Run the minimum Phase 0 live matrix against the exact commit installed in the real Odoo environment. Start with `P0-REAL-HELLO`, `P0-REAL-READ` and `P0-REAL-ACTION`, then controlled failure pairs.

If the captured evidence reveals a bug in the measurement tooling, create the smallest Phase-0 corrective slice, fix it, run deterministic tests in an environment that can actually execute them, and repeat the affected real validation.

If the aggregate gate passes, update this file:

```text
phase: 1
phase_state: READY
active_slice: P1.1-provider-event-contract
active_slice_state: READY
```

Do not start Phase 1 before that transition is evidence-backed.

## Planned Phase 1 slices

These are provisional until Phase 0 closes and current code is re-inspected:

- `P1.1-provider-event-contract` — define/freeze provider-neutral event/lifecycle port;
- `P1.2-codex-conformance-fixtures` — current adapter protocol fixture/conformance suite;
- `P1.3-sdk-spike` — compare official Codex SDK against the same conformance contract;
- `P1.4-forward-compatibility` — benign unknown notifications vs unsafe unknown server requests;
- `P1.5-cancellation-and-errors` — structured provider terminal/cancel semantics;
- `P1.6-real-soak` — `P1-REAL-SOAK-100` and related live gates;
- `P1.7-provider-decision` — choose/record custom adapter vs SDK based on evidence.

Do not treat this provisional list as permission to implement it while Phase 0 is open.

## Validation policy

- Tests only count when they were actually executed.
- Real validation only counts against the exact commit materially under test.
- A coding/ChatGPT run without Odoo+Codex access must leave the state at `REAL_ENV_VALIDATION_REQUIRED` when that is the real blocker.
- Failed live validation creates a corrective child slice; it does not permit skipping the gate.

## Automation policy

The execution loop may be resumed by an hourly ChatGPT task or another authorized session using `CONTINUOUS_EXECUTION_PROTOCOL.md`.

A 40-minute ChatGPT schedule is not supported by the current task scheduler; hourly is the minimum supported recurrence.

**Do not use GitHub Actions. No runners/workers are available for this roadmap.** No phase or slice may depend on GitHub Actions for execution or validation.

## Blockers

Current blocker:

```text
REAL_ENVIRONMENT_EVIDENCE_MISSING
```

Meaning: the code/repository has enough Phase 0 tooling to request the live evidence, but this repository-only execution context cannot honestly produce the browser + authenticated Odoo/Codex observations required by the Phase 0 exit gate.

## Resume instructions

Every new run must:

1. re-read current `main` and this file;
2. inspect whether new live evidence or implementation commits appeared;
3. process that evidence before selecting new work;
4. follow `CONTINUOUS_EXECUTION_PROTOCOL.md`;
5. update this cursor before finishing.