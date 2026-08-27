# Phase 1 — provider boundary stabilization

Date: 2026-08-27  
Inspected main: `b86a64bcd0a76cee44a5efe090dc6f067459f585`  
Status: `IN_PROGRESS`

## Goal

Stabilize the Codex provider boundary around the Odoo-owned host loop before changing failure
semantics, public activity, answer streaming or chat UX.

The validated Phase 0 architecture is authoritative:

```text
Codex proposes one NextDecision
  -> Odoo validates the decision
  -> Odoo executes REASONING capabilities with the effective user and su=False
  -> PLAN proposals remain stage-only
  -> Odoo owns preview, policy, approval, write barrier, execution and verification
```

Provider-side dynamic tool execution from the pre-convergence playbook is therefore no longer a
valid target contract.

## P1.1 — conformance rebase and minimum provider port

State: `COMPLETE`

Objective:

- rebase the prepared Codex conformance manifest onto the validated one-decision host loop;
- define the smallest provider-neutral port the current host actually needs;
- preserve the existing custom Codex adapter and all Odoo authority semantics;
- do not add another provider and do not choose SDK-vs-custom yet.

Changes:

- conformance format advances to v2;
- obsolete provider-side `dynamic_tool_mapping`, `capability_success` and `capability_failure`
  cases are replaced by `reasoning_decision_mapping`, `plan_decision_mapping` and
  `final_answer_mapping`;
- `ReasoningProvider` is the minimal structural port: one async `next_decision(...) -> NextDecision`;
- the port is exported without changing `AgentTurnService` runtime composition yet;
- a dependency-light AST regression proves the port signature matches the current
  `CodexDecisionEngine.next_decision` signature.

Deterministic validation actually executed for P1.1:

```text
python -m pytest -q tests/unit/test_codex_provider_conformance.py
5 passed in 0.08s

python -m py_compile \
  tests/contracts/codex_provider_conformance.py \
  addons/odoo_ai_assistant/runtime/agent/provider.py
PASS
```

## P1.2 — current adapter conformance binding

State: `COMPLETE`

Objective:

- bind the existing custom `CodexDecisionEngine` to the v2 conformance contract;
- record what the current code actually satisfies without repairing behavior to make the matrix green;
- use the result to choose the smallest next compatibility repair.

Binding:

- `tests/contracts/current_codex_decision_conformance.py` observes the committed custom decision
  adapter plus shared Codex protocol implementation using dependency-light source checks;
- observations contain only contract-level booleans/outcomes, never prompts, provider stdout/stderr,
  business values, credentials or private reasoning;
- `tests/unit/test_codex_provider_conformance.py` locks the observed matrix so later changes must
  intentionally move cases from FAIL to PASS.

Observed matrix on inspected `main`:

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

Interpretation:

1. `unknown_notification` fails because `_validate_notification()` currently rejects an unrecognized
   method with `codex_event_not_allowed`. This is the smallest forward-compatibility gap.
2. `terminal_failure` fails because terminal provider errors are mostly reduced to
   `codex_turn_failed`; only the known invalid-output-schema case currently receives a distinct code.
3. `overload_backpressure` fails because terminal overload/rate-limit conditions do not have an
   explicit sanitized retryable classification. Provider-owned `willRetry=true` events may continue,
   but the host contract has no retryable terminal class yet.

No runtime behavior was changed in P1.2.

## P1.2 deterministic validation status

Added/updated:

```text
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
```

Not executed in this run because the connected GitHub path exposes repository read/write but no
repository-capable Python runner:

```text
python -m pytest -q tests/unit/test_codex_provider_conformance.py
python -m py_compile tests/contracts/current_codex_decision_conformance.py
```

No GitHub Actions were used. The 11/14 matrix is a direct source-observation result, not a claim that
the newly added pytest test ran.

## Invariants

- Odoo remains operational and persistence authority.
- Effective-user capability execution remains `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider output is untrusted and host-validated.
- PLAN remains proposal-only before the existing action lifecycle.
- No SQL/Python/shell/sudo/unrestricted ORM escape hatch is introduced.
- Codex credentials remain provider-owned.
- No provider, bundle or skill abstraction is introduced.

## Validation debt

Phase 1 mandatory real-environment debt remains open:

- `P1-REAL-SOAK-100` — HARD before Phase 1 completion;
- `P1-REAL-TOOLCALL` — HARD before Phase 1 completion;
- `P1-REAL-CANCEL` — HARD before Phase 1 completion;
- `P1-REAL-VERSION` — HARD before Phase 1 completion.

P1.2 itself changes no active provider behavior, so these gates are not newly invalidated by this
slice. Any behavior-changing Phase 1 repair must be validated on its exact implementation SHA before
Phase 1 closes.

## Exact next action

Execute `P1.3-benign-unknown-notification-tolerance` as the smallest failing compatibility boundary.
Accept genuinely unknown benign notification methods without changing critical event validation.
Malformed known events and thread/turn identity mismatches must continue to fail closed. Add focused
deterministic regressions. Do not combine terminal failure preservation or overload/backpressure
classification into that repair slice.
