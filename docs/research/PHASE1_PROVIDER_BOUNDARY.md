# Phase 1 — provider boundary stabilization

Date: 2026-08-27  
Inspected implementation/test checkpoint: `012e9c8888011e70d8029d18f028a155f1d5a868`
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

Observed matrix at P1.2:

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

No runtime behavior was changed in P1.2.

## P1.3 — benign unknown-notification tolerance

State: `REAL_ENV_VALIDATION_REQUIRED`

Objective:

- repair only the smallest forward-compatibility failure identified by P1.2;
- allow additive unknown notifications to remain inert instead of killing an otherwise valid turn;
- preserve fail-closed behavior for known malformed/identity-critical events and all server requests;
- leave terminal-error preservation and overload/backpressure classification for later slices.

Implementation:

- `CodexDecisionEngine` now routes notification validation through
  `_validate_decision_notification()`;
- the helper first delegates to the existing shared `_validate_notification()` so all known Codex
  methods preserve their existing strict validation;
- only the specific `codex_event_not_allowed` result is treated as an additive unknown method;
- unknown notifications require a non-empty bounded method and object params;
- a mismatched `threadId` or `turnId` fails with `codex_event_identity_mismatch`;
- any unknown notification containing an unverified `callId` fails with
  `codex_event_identity_unverified`;
- a JSON-RPC server request carrying top-level `id` remains rejected before this helper is reached;
- tolerated unknown notifications are ignored: they cannot execute a capability, stage a plan or
  create a host effect.

This keeps provider output untrusted and does not change Odoo authority, effective-user execution,
PLAN/write lifecycle, credentials or persistence.

## P1.3 deterministic/eval coverage

Updated:

```text
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
```

The conformance binding now marks `unknown_notification` accepted only when the bounded helper and
its identity guards exist. The focused unit regression extracts the exact helper from committed
source and exercises:

- benign unknown telemetry notification: accept/ignore;
- matching thread/turn-scoped unknown notification: accept/ignore;
- malformed empty method: reject;
- mismatched thread identity: reject;
- mismatched turn identity: reject;
- unverified `callId`: reject;
- known critical validator failure: propagate unchanged.

The first local execution exposed a separate false negative in the P1.2 source binding. The
`final_answer_mapping` observer searched for the quoted literal `"final_answer"` only in
`codex_decision.py`, although that adapter delegates decoding to `parse_next_decision()` and the
authoritative kind branch and `FinalAnswer` construction live in `contracts.py`. Consequently the
runtime mapping existed, but the static observer reported a third failed case:

```text
focused conformance before correction: 6 passed, 1 failed
full unit suite before correction: 176 passed, 1 failed
unexpected failed case: final_answer_mapping
```

Checkpoint `012e9c8888011e70d8029d18f028a155f1d5a868` repairs the harness without changing
runtime behavior. The observer now verifies the adapter delegation and the shared parser branch for
all three decision kinds. A focused regression proves final-answer conformance does not depend on a
prompt literal.

Static contract projection after P1.3:

```text
12 PASS / 2 FAIL
remaining: terminal_failure, overload_backpressure
```

Deterministic validation actually executed after the harness correction:

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

The dependency-light P1.3 projection is therefore executable and green at the recorded checkpoint:
12/14 conformant, with only the intentionally unresolved `terminal_failure` and
`overload_backpressure` cases failing their conformance expectations.

The Odoo suite and `P1-REAL-VERSION` / `P1-REAL-SOAK-100` were not executed against this checkpoint.
The available Odoo service had started before the checkout was updated and the current execution
user could not restart/update that service or authenticate to its test database. Codex CLI
`0.149.1` was observed locally, but version presence alone is not the exact-SHA real gate.

## Invariants

- Odoo remains operational and persistence authority.
- Effective-user capability execution remains `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider output is untrusted and host-validated.
- PLAN remains proposal-only before the existing action lifecycle.
- Unknown server requests remain rejected; notification tolerance grants no host authority.
- No SQL/Python/shell/sudo/unrestricted ORM escape hatch is introduced.
- Codex credentials remain provider-owned.
- No provider, bundle or skill abstraction is introduced.

## Validation debt

P1.3 changes active provider protocol behavior, so it is not complete until exact-SHA real evidence
exists for the compatibility boundary. The exact commit to validate is the `main` publication commit
containing this record.

Immediate HARD gate before another dependent provider-behavior slice:

- `P1-REAL-VERSION` — record the supported Codex version and verify startup/initialize/thread/turn
  behavior on the exact P1.3 publication SHA;
- `P1-REAL-SOAK-100` — run at least 100 greeting/simple-read turns on that exact revision and require
  zero protocol-shape failures, zero authority bypasses and zero wrong-turn/call bindings.

Phase 1 completion debt that remains open independently:

- `P1-REAL-TOOLCALL` — HARD before Phase 1 completion;
- `P1-REAL-CANCEL` — HARD before Phase 1 completion.

## Exact validation procedure

Use `docs/research/REAL_ENV_VALIDATION_PROTOCOL.md` with the addon installed/updated from the exact
P1.3 publication commit.

For `P1-REAL-VERSION`, record Odoo 18 version, exact Codex version and successful
startup/initialize/thread/turn protocol behavior.

For `P1-REAL-SOAK-100`, run at least 100 turns composed of trivial greetings and simple reads and
capture completion count, protocol-shape failures, provider process failures, median/p95 latency,
unexpected retries and unknown-notification diagnostics. PASS requires:

```text
protocol-shape failures = 0
host-authority bypasses = 0
wrong-turn/call binding = 0
```

Commit only sanitized evidence with validation IDs and exact SHA. Do not commit credentials, raw
prompts, provider stdout/stderr, unrestricted tool payloads or private reasoning.

## Exact next action

Wait for committed `P1-REAL-VERSION` and `P1-REAL-SOAK-100` evidence against the exact P1.3
publication SHA. If both PASS, clear only those debt items and reconstruct the next provider repair
from current `main`. If either fails, freeze later provider work and implement the smallest repair
for the observed boundary. Do not begin terminal-error preservation or overload/backpressure work
before this HARD gate is processed.
