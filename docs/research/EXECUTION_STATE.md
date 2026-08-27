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
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
blocking_validations: P1-REAL-SOAK-100, P1-REAL-VERSION
next_slice: BLOCKED_PENDING_P1.3_REAL_ENV
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

No commit newer than the P1.2 checkpoint `2bf5fdd7c96a0729a8eb03f6bbdf0d9e3dc246f5` existed when this
run reconstructed `main`. No newer real-environment failure or passing handoff was therefore
available to process before selecting P1.3.

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
```

The executed conformance projection is 12/14. Only the intentionally unresolved
`terminal_failure` and `overload_backpressure` cases remain non-conformant.

## Tests not executed

```text
Odoo addon test suite at 012e9c8888011e70d8029d18f028a155f1d5a868
P1-REAL-VERSION
P1-REAL-SOAK-100
```

The available Odoo service was started before the checkout update and did not have this exact
checkpoint loaded. The current execution user could not restart/update that service or authenticate
to its test database. Codex CLI `0.149.1` was observed locally, but its presence alone is not
`P1-REAL-VERSION`; the exact-SHA Odoo+Codex gate remains required.

## Validation debt

P1.3 materially changes provider protocol behavior. Its publication commit must therefore be tested
as the exact installed addon revision before another dependent provider-behavior slice proceeds.
The exact publication SHA is the `main` commit containing this state record and must be copied into
the real-environment evidence.

```text
P1-REAL-SOAK-100
  gate_type: HARD
  origin_slice: P1.3-benign-unknown-notification-tolerance
  commit_materially_tested: pending exact P1.3 publication HEAD
  downstream_scope_blocked: further dependent provider-behavior work and Phase 2+
  reason: prove additive provider notifications no longer cause protocol-shape turn failures

P1-REAL-VERSION
  gate_type: HARD
  origin_slice: P1.3-benign-unknown-notification-tolerance
  commit_materially_tested: pending exact P1.3 publication HEAD
  downstream_scope_blocked: further dependent provider-behavior work and Phase 2+
  reason: bind the compatibility result to the supported Codex App Server version/protocol
```

Other Phase 1 completion debt remains open but was not created by P1.3:

```text
P1-REAL-TOOLCALL | HARD | host/provider capability mapping | Phase 2+
P1-REAL-CANCEL   | HARD | provider turn identity/cancellation | Phase 2+
```

## Required real-environment procedure

Validate the exact P1.3 publication SHA under the assumptions in
`REAL_ENV_VALIDATION_PROTOCOL.md`.

1. `P1-REAL-VERSION`: install/update the addon from the exact publication SHA, record Odoo 18 and
   Codex versions, and verify startup/initialize/thread/turn behavior on that exact supported Codex
   runtime.
2. `P1-REAL-SOAK-100`: run at least 100 turns composed of trivial greetings and simple reads.
3. Capture completion count, protocol-shape failures, provider process failures, median/p95 latency,
   unexpected retries and any unknown-notification diagnostics.
4. PASS requires `protocol-shape failures = 0`, `host-authority bypasses = 0` and
   `wrong-turn/call binding = 0`.
5. Commit sanitized evidence containing both validation IDs, exact commit tested, Odoo/Codex
   versions and PASS/FAIL outcome. Do not commit credentials, prompts, provider stdout/stderr or
   unrestricted business payloads.

## Exact next action

Do not implement the remaining `terminal_failure` or `overload_backpressure` repairs yet. First
process committed PASS/FAIL evidence for `P1-REAL-VERSION` and `P1-REAL-SOAK-100` against the exact
P1.3 publication SHA. On PASS, clear only those debt items and reconstruct the next Phase 1 repair
from current `main`; on FAIL, select the smallest corrective slice for the observed boundary.
