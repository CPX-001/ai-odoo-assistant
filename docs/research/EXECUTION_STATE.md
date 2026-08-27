# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 1
phase_name: provider boundary stabilization
phase_state: IN_PROGRESS
active_phase_record: docs/research/PHASE1_PROVIDER_BOUNDARY.md
active_slice: P1.3-benign-unknown-notification-tolerance
active_slice_state: COMPLETE
current_gate_type: NONE
blocking_validations: NONE_FOR_NEXT_SLICE
phase_completion_validations: P1-REAL-TOOLCALL, P1-REAL-CANCEL
next_slice: P1.4-terminal-failure-preservation
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

The installed Odoo instance was explicitly updated from exact checkpoint
`49bdac1f732acaaee3154ed60baffd675130991a`. The selected Odoo regression battery passed 46 test
methods with zero failures/errors. `P1-REAL-VERSION` passed on Odoo 18.0 Community with Codex
0.149.1 and an authenticated provider-owned account under Odoo's `data_dir`.

`P1-REAL-SOAK-100` then passed 100/100 normal product-path turns: 80 greetings and 20 simple reads,
with zero protocol-shape failures, provider-process failures, runtime-unavailable retries,
host-authority bypasses, wrong-turn/call bindings or read tool-boundary failures. Median latency was
7818.479 ms and p95 was 34563.910 ms. Six bounded `field_not_in_schema` corrections completed
normally and were not classified as provider failures. Sanitized evidence is recorded in
`docs/research/evidence/phase1/2026-08-27/P1-REAL-VERSION-SOAK-49bdac1.md`.

## P1.3 implementation

P1.3 repairs only the active one-decision adapter's additive-notification compatibility boundary.
The shared legacy Codex protocol validator remains strict; `CodexDecisionEngine` now wraps it with a
bounded compatibility rule:

- known notifications still go through the existing validator unchanged;
- an unknown method is tolerated only after the shared validator identifies it specifically as
  `codex_event_not_allowed`;
- malformed/empty/oversized unknown notification methods or non-object params fail closed;
- an unknown notification carrying a mismatched `threadId` or `turnId` fails closed;
- an unknown notification carrying any unverified `callId` fails closed;
- server requests remain rejected before notification handling because an event carrying a JSON-RPC
  request `id` never reaches the compatibility helper;
- the event is otherwise inert: it is ignored and cannot execute a capability or create host effects.

No terminal-error normalization, overload/backpressure classification, provider replacement, SDK
adapter or capability/action behavior is included in this slice.

## Tests added or updated

- `tests/contracts/current_codex_decision_conformance.py` now requires the bounded compatibility
  helper and its identity guards before classifying `unknown_notification` as accepted;
- `tests/unit/test_codex_provider_conformance.py` adds a dependency-light executable regression that
  extracts the exact compatibility helper from committed source and verifies benign tolerance,
  malformed rejection, thread/turn mismatch rejection, unverified `callId` rejection and propagation
  of a known critical-event failure;
- the expected static conformance projection moves from 11/14 to 12/14, leaving only
  `terminal_failure` and `overload_backpressure` unresolved.

## Deterministic harness correction

The first repository-capable execution of the P1.3 tests found one false negative inherited from
the P1.2 static binding:

```text
focused conformance before correction: 6 passed, 1 failed
full unit suite before correction: 176 passed, 1 failed
unexpected failed case: final_answer_mapping
```

The runtime mapping was present. `CodexDecisionEngine` delegates the provider envelope to
`parse_next_decision()`, while the `final_answer` branch and `FinalAnswer` construction are defined
in the shared `contracts.py`. The observer incorrectly required the quoted kind literal to appear
in `codex_decision.py`, so prompt/source layout rather than the executable contract determined the
result.

Checkpoint `012e9c8888011e70d8029d18f028a155f1d5a868` makes the dependency-light binding inspect
the adapter delegation plus the shared parser branch for all three decision kinds. A regression
proves the final-answer observation remains valid without a prompt literal. No product runtime or
provider behavior changed in this correction.

## Tests actually executed

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_provider_conformance.py
8 passed in 0.11s

.venv/bin/python -m pytest -q tests/unit
178 passed in 2.26s

.venv/bin/python -m pytest -q \
  tests/e2e/test_e2e_convergence_battery.py \
  tests/e2e/test_e2e_decision_sequences.py \
  tests/e2e/test_next_decision_contract.py \
  tests/e2e/test_working_transcript_contract.py \
  tests/e2e/test_canonical_plan_proposal.py
29 passed in 0.12s

python3 -m py_compile \
  tests/contracts/codex_provider_conformance.py \
  tests/contracts/current_codex_decision_conformance.py \
  addons/odoo_ai_assistant/runtime/agent/provider.py \
  addons/odoo_ai_assistant/runtime/agent/codex_decision.py
PASS

git diff --check
PASS

installed Odoo addon update at 49bdac1f732acaaee3154ed60baffd675130991a
PASS

selected Odoo queue/runtime/host-loop/convergence/PLAN/adapter/capability/action suites
46 tests, 0 failed, 0 errors

P1-REAL-VERSION
PASS — Odoo 18.0 Community, Codex 0.149.1, runtime account authenticated

P1-REAL-SOAK-100
PASS — 100/100 completed; 80 greetings, 20 reads; median 7818.479 ms, p95 34563.910 ms
protocol/provider-process/authority/binding/read-tool-boundary failures: 0
runtime_unavailable retries: 0

fixture cleanup and installed-service health
PASS — fixture counts returned to zero; Odoo active; HTTP 200
```

The executed conformance projection is 12/14. Only the intentionally unresolved
`terminal_failure` and `overload_backpressure` cases remain non-conformant.

## Tests not executed

```text
P1-REAL-TOOLCALL
P1-REAL-CANCEL
```

These are independent Phase 1 completion gates and were not silently inherited from the P1.3 soak.

## Validation debt

P1.3 debt cleared:

```text
P1-REAL-SOAK-100 | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
P1-REAL-VERSION  | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
```

Independent Phase 1 completion debt remains open:

```text
P1-REAL-TOOLCALL | HARD | host/provider capability mapping | Phase 2+
P1-REAL-CANCEL   | HARD | provider turn identity/cancellation | Phase 2+
```

## Exact next action

Select P1.4 to preserve bounded structured provider terminal-failure information, the first
remaining failed conformance case. Keep overload/backpressure classification as a separate later
slice. Preserve the validated one-decision host loop, add deterministic regression coverage and
define any new real-environment debt before implementation. Do not mark Phase 1 complete until
`P1-REAL-TOOLCALL` and `P1-REAL-CANCEL` also pass.
