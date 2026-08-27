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
active_slice: P1.2-current-adapter-conformance-binding
active_slice_state: COMPLETE
current_gate_type: NONE
next_slice: P1.3-benign-unknown-notification-tolerance
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

No newer committed real-environment failure or handoff evidence exists after P1.1 at
`b86a64bcd0a76cee44a5efe090dc6f067459f585`. The latest real product-path evidence remains the
passing Phase 0 exact-SHA handoff, so Phase 1 may continue.

## P1.2 published content

P1.2 binds the current custom `CodexDecisionEngine` to the v2 conformance harness without changing
runtime behavior. The binding is dependency-light and source-observational: it reads the committed
custom adapter and shared Codex protocol implementation and emits only sanitized contract facts.
It is not presented as a live App Server probe.

Current adapter matrix:

```text
PASS initialize
PASS thread_isolation
PASS turn_output_schema
PASS agent_message_delta
PASS completed_agent_message
PASS reasoning_decision_mapping
PASS plan_decision_mapping
PASS final_answer_mapping
FAIL unknown_notification
PASS malformed_critical_event
PASS identity_mismatch
PASS cancellation
FAIL terminal_failure
FAIL overload_backpressure

11 PASS / 3 FAIL
```

Observed failing boundaries:

- `unknown_notification`: the shared notification validator ends unknown methods with
  `codex_event_not_allowed` instead of safely ignoring a benign forward-compatible notification;
- `terminal_failure`: `_decision_failure_code()` preserves only the known invalid-output-schema
  special case and otherwise collapses provider terminal detail to `codex_turn_failed`;
- `overload_backpressure`: the current adapter has no explicit sanitized retryable overload/rate-limit
  classification. `willRetry=true` provider events are allowed to continue internally, but terminal
  overload is not exposed as the v2 retryable class.

The smallest compatibility repair is unknown-notification tolerance. It is independent of failure
semantics redesign and must remain bounded so malformed/identity-bearing critical events continue
to fail closed.

## Tests added or updated

- added `tests/contracts/current_codex_decision_conformance.py` as the current custom-adapter binding;
- extended `tests/unit/test_codex_provider_conformance.py` with the exact expected 11/14 matrix and
  the three observed failing case IDs.

## Tests actually executed

No repository test runner is available through the connected GitHub execution path in this run.
No GitHub Actions were used. The matrix above is a direct sanitized inspection result from current
`main`, not a claim that the newly added pytest assertion was executed.

## Tests not executed

```text
python -m pytest -q tests/unit/test_codex_provider_conformance.py
python -m py_compile tests/contracts/current_codex_decision_conformance.py
```

These remain deterministic validation to execute when a repository-capable Python runner is
available. Real Codex App Server behavior remains governed by the Phase 1 live gates below.

## Remaining validation debt

All Phase 0 mandatory hard debt is closed.

Phase 1 mandatory completion debt:

```text
P1-REAL-SOAK-100 | HARD | provider boundary | Phase 2+
P1-REAL-TOOLCALL | HARD | host/provider capability mapping | Phase 2+
P1-REAL-CANCEL   | HARD | provider turn identity/cancellation | Phase 2+
P1-REAL-VERSION  | HARD | supported Codex protocol/version | Phase 2+
```

P1.2 changes no active provider behavior, so it does not itself invalidate the passing Phase 0
product-path evidence or create a new exact-SHA real-environment gate.

## Exact next action

Execute `P1.3-benign-unknown-notification-tolerance`:

1. change only the current Codex notification compatibility boundary so genuinely unknown benign
   notification methods are ignored safely;
2. preserve fail-closed validation for malformed events and any known event carrying thread/turn or
   other critical identity;
3. add focused deterministic regressions for benign unknown notification tolerance and malformed /
   identity mismatch rejection;
4. do not combine terminal structured-error preservation or overload classification into this slice;
5. after the behavior-changing repair, attach the relevant exact-SHA Phase 1 real-environment debt
   before Phase 1 can complete.
