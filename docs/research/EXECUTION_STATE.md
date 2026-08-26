# Stabilization execution state

State format: 2  
Updated: 2026-08-26  
Product/code baseline inspected: `4eb8502e04f54feccc5ad47a69fb5d0a51910416`  
Execution protocol revision introduced at: `278f3cc2b8899b5e3ca1c9c34287e8049ba4ba50`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0-LIVE-BASELINE
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 0
currently_stacked_unvalidated_contract_layers: 0
```

These are default safety limits, not targets to consume.

The purpose is to batch compatible real Odoo+Codex tests without accumulating several dependent architecture layers that may all need rework after one failed validation.

## Current fact pattern

Phase 0 implementation tooling is already present and documented in `PHASE0_BASELINE.md`:

- machine-readable scenario matrix;
- browser/provider timing instrumentation;
- redacted live Odoo HTTP capture runner;
- one-trace summarizer;
- aggregate Phase 0 gate evaluator.

The remaining Phase 0 exit gate depends on real Odoo 18 + authenticated/configured Codex evidence.

Phase 0 is a **hard gate for architecture-changing provider/runtime work** because its purpose is to measure latency/failure behavior before those mechanisms are redesigned.

It does not need to block repository work that remains valid regardless of the live baseline result.

## Active slice — P0-LIVE-BASELINE

Objective: collect enough real-environment evidence for `phase0_report.py` to decide whether the mainline Phase 1 refactor may start.

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
- [ ] `tests/e2e/phase0_report.py` returns `ready_for_phase1=true` on collected evidence.

Reference procedure: `REAL_ENV_VALIDATION_PROTOCOL.md` and `PHASE0_BASELINE.md`.

## Validation debt

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-HELLO
  - P0-REAL-READ
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
origin_slice: P0-LIVE-BASELINE
commit_materially_tested: pending
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
  - architecture decisions based on measured latency/failure attribution
reason: real Odoo+Codex evidence is not available in repository-only execution context
```

This debt prevents the main provider refactor, but does not prevent explicitly authorized preparation work below.

## Authorized look-ahead while Phase 0 evidence is pending

### P1-PREP-CONFORMANCE — READY

Purpose: prepare reusable Codex protocol/conformance fixtures and a test harness against the **current** adapter without changing product runtime behavior.

Allowed scope:

- inspect the current Codex adapter and supported protocol shapes;
- capture/create sanitized deterministic protocol fixtures;
- build reusable conformance test helpers;
- cover initialize/thread/turn/agent-message/tool-call/error/cancel protocol shapes where possible without changing runtime semantics;
- document gaps that an eventual current-adapter-vs-official-SDK spike must compare.

Explicitly out of scope until Phase 0 hard gate passes:

- replacing the current Codex adapter;
- changing the `ReasoningEngine` production contract;
- changing provider process lifetime;
- changing product streaming semantics;
- changing production unknown-notification behavior;
- optimizing startup based on guessed latency.

Why look-ahead is safe: fixtures/harness remain useful whichever provider implementation is chosen and do not consume an unvalidated new production contract.

Gate metadata:

```text
gate_type: SOFT for preparation completion
lookahead_eligible: yes
depends_on_unvalidated_contracts: none
creates_new_production_contract: no
lookahead_budget_cost: 0 production contract layers
```

After this preparation slice is complete, do not automatically start additional Phase 1 production slices while `VD-P0-LIVE-BASELINE` remains unresolved unless this file is updated with a newly researched eligible slice.

## Exact next action selection

Use this priority:

1. If real Phase 0 evidence is available, process it first and run `phase0_report.py`.
2. If no live evidence is available and `P1-PREP-CONFORMANCE` is not complete, that preparation slice may be executed.
3. If the prep slice is complete and live evidence is still absent, stop and report `VD-P0-LIVE-BASELINE`; do not invent more speculative provider work.
4. If Phase 0 gate passes, transition to normal Phase 1 execution.

## Planned Phase 1 mainline slices

Provisional until Phase 0 closes and current code is re-inspected:

- `P1.1-provider-event-contract` — define/freeze provider-neutral event/lifecycle port;
- `P1.2-codex-conformance-fixtures` — reconcile/adopt preparation fixtures into mainline conformance suite;
- `P1.3-sdk-spike` — compare official Codex SDK against the same conformance contract;
- `P1.4-forward-compatibility` — benign unknown notifications vs unsafe unknown server requests;
- `P1.5-cancellation-and-errors` — structured provider terminal/cancel semantics;
- `P1.6-real-soak` — `P1-REAL-SOAK-100` and related live gates;
- `P1.7-provider-decision` — choose/record custom adapter vs SDK based on evidence.

Do not treat this list as permission to stack Phase 1 through Phase 3 while provider contracts remain unvalidated.

## Phase transition policy

Formal completion still requires the full phase gate.

Bounded look-ahead is allowed only according to `CONTINUOUS_EXECUTION_PROTOCOL.md` and does not turn an incomplete phase into a complete one.

For the stabilization chain:

```text
Phase 1 provider boundary
  -> Phase 2 failure semantics
  -> Phase 3 public activity
  -> Phase 4 answer streaming
  -> Phase 5 chat UX
```

assume downstream dependency unless proven otherwise. Prefer batching real validations across one or two compatible slices, not across two or three whole dependent phases.

## Validation policy

- Tests count only when actually executed.
- Real validation counts only against the exact materially tested commit.
- A coding/ChatGPT run without Odoo+Codex access records validation debt rather than claiming success.
- Failed hard validation freezes dependent look-ahead work and creates the smallest corrective slice.
- A slice may proceed with unresolved soft validation only while the configured look-ahead budget remains available.
- A downstream slice may not consume an unvalidated new contract if doing so would create another stacked contract layer.

## Automation policy

The execution loop may be resumed by an hourly ChatGPT task or another authorized session using `CONTINUOUS_EXECUTION_PROTOCOL.md`.

A 40-minute ChatGPT schedule is not supported by the current task scheduler; hourly is the minimum supported recurrence.

**Do not use GitHub Actions for this roadmap. No runners/workers are available.** Existing workflows are not an execution or validation dependency for this plan.

## Current blocker

```text
REAL_ENVIRONMENT_EVIDENCE_MISSING
```

This blocker is scoped: it blocks Phase 0 closure and Phase 1 production architecture changes, but not the explicitly authorized `P1-PREP-CONFORMANCE` preparation slice.

## Resume instructions

Every new run must:

1. re-read current `main` and this file;
2. inspect whether new live evidence or implementation commits appeared;
3. process available validation evidence before consuming more look-ahead budget;
4. follow `CONTINUOUS_EXECUTION_PROTOCOL.md`;
5. select only normal-ready or explicitly look-ahead-eligible slices;
6. update this cursor, validation debt and budget consumption before finishing.
