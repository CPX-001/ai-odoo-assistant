# Phase 1 — provider boundary stabilization

Date: 2026-08-27
Inspected implementation/test base: `035cc801fc9b0de6c401837274d4b6054c34c3d6`
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

No runtime implementation was changed in P1.2.

## P1.3 — benign unknown-notification tolerance

State: `COMPLETE`

Objective:

- repair only the smallest forward-compatibility failure identified by P1.2;
- allow additive unknown notifications to remain inert instead of killing an otherwise valid turn;
- preserve fail-closed behavior for known malformed/identity-critical events and all server requests;
- leave terminal-error preservation and overload/backpressure classification for later slices.

Implementation:

- `CodexDecisionEngine` routes notification validation through
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

The conformance binding marks `unknown_notification` accepted only when the bounded helper and
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
runtime behavior. The observer verifies the adapter delegation and the shared parser branch for
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

The dependency-light P1.3 projection is executable and green at the recorded checkpoint:
12/14 conformant, with only the intentionally unresolved `terminal_failure` and
`overload_backpressure` cases failing their conformance expectations.

Real validation was subsequently executed on the installed Odoo instance after explicitly updating
the addon from `49bdac1f732acaaee3154ed60baffd675130991a`:

```text
Odoo 18.0 Community / Codex 0.149.1
runtime account: authenticated
selected Odoo regression battery: 46 tests, 0 failed, 0 errors
P1-REAL-VERSION: PASS
P1-REAL-SOAK-100: PASS
soak composition: 80 greetings, 20 simple reads
completion: 100/100
protocol-shape failures: 0
provider process failures: 0
runtime_unavailable retries: 0
host-authority bypasses: 0
wrong-turn/call bindings: 0
read tool-boundary failures: 0
latency median/p95: 7818.479 / 34563.910 ms
```

Six reads required the existing bounded `field_not_in_schema` correction and then completed. This
was recorded separately from provider failures and retries. The dedicated user, partner, 100 turns
and 100 conversations were removed after aggregation; Odoo was restarted and returned HTTP 200.
The sanitized evidence is
`docs/research/evidence/phase1/2026-08-27/P1-REAL-VERSION-SOAK-49bdac1.md`.

## P1.4 — bounded terminal-failure preservation

State: `COMPLETE`

Objective:

- close only the `terminal_failure` conformance gap;
- preserve machine-readable provider terminal facts across the Codex decision adapter boundary;
- never preserve raw provider messages or `additionalDetails`;
- retain current host/product error codes and leave retry/backpressure semantics for a separate slice.

Implementation:

- terminal decision failures now raise `CodexDecisionError`, a `CodexAgentError` subtype carrying an
  optional immutable `CodexProviderFailure`;
- `CodexProviderFailure` is deliberately small: `category`, `http_status_code` and `upstream_code`;
- provider categories and upstream codes must be bounded ASCII machine tokens;
- HTTP status is retained only when it is an integer in the 100-599 range;
- string and structured-object `codexErrorInfo` shapes are supported;
- a bounded JSON provider `message` may be parsed only to extract a machine error code and HTTP
  status; the original message text is not attached to the exception;
- `additionalDetails`, request bodies and any other provider payload are ignored;
- invalid/unbounded fields are discarded instead of copied;
- both terminal top-level `error` events and failed `turn/completed` events use the same projection;
- existing `invalid_json_schema -> codex_output_schema_invalid` behavior remains intact;
- all other terminal failures retain `codex_turn_failed` as the current sanitized product code.

`serverOverloaded` is now preservable as a provider category, but it remains `codex_turn_failed`
and is not marked retryable in P1.4. There is still no automatic provider/capability/write retry.

This slice does not define the Phase 2 failure taxonomy, browser presentation, retry buttons or
effect-state semantics. Its only purpose is to stop destroying bounded provider facts before that
later host-owned mapping exists.

## P1.4 deterministic/eval coverage

Added or updated:

```text
addons/odoo_ai_assistant/runtime/agent/codex_decision.py
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
tests/unit/test_codex_terminal_failure_projection.py
```

The new dependency-light regression extracts the exact P1.4 classes/helpers from the modified source
and verifies:

- a captured-style `invalid_json_schema` terminal error keeps category `other`, HTTP 400 and the
  upstream machine code while the raw schema detail is absent;
- structured `httpConnectionFailed` keeps only category + HTTP status;
- invalid/unbounded provider fields are discarded;
- `serverOverloaded` is retained only as a fact and is deliberately not classified retryable yet;
- both terminal routes call the same bounded terminal-error projection;
- the current conformance binding reports `structured_error_preserved = true`.

Actually executed in the available ChatGPT execution sandbox against the exact modified source
snapshot prepared for publication:

```text
python -m pytest -q tests/unit/test_codex_terminal_failure_projection.py
5 passed in 0.06s

python -m py_compile \
  addons/odoo_ai_assistant/runtime/agent/codex_decision.py \
  tests/contracts/current_codex_decision_conformance.py \
  tests/unit/test_codex_provider_conformance.py \
  tests/unit/test_codex_terminal_failure_projection.py
PASS
```

The full repository/Odoo suites were not available through the connected GitHub interface and are
not claimed as executed.

Static contract projection after P1.4:

```text
13 PASS / 1 FAIL
remaining: overload_backpressure
```

P1.4 adds no new mandatory real-environment validation ID because it does not change tool
execution, writes, retry policy, cancellation or browser failure presentation. The real Phase 1
completion gates below remain required, and Phase 2 will add real validation for the eventual
user-visible failure families.

## Invariants

- Odoo remains operational and persistence authority.
- Effective-user capability execution remains `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider output is untrusted and host-validated.
- PLAN remains proposal-only before the existing action lifecycle.
- Unknown server requests remain rejected; notification tolerance grants no host authority.
- Preserved provider failure facts are diagnostic data only and grant no host authority.
- Raw provider messages/details are not retained by the P1.4 projection.
- No automatic retry or effect inference is introduced by terminal-failure preservation.
- No SQL/Python/shell/sudo/unrestricted ORM escape hatch is introduced.
- Codex credentials remain provider-owned.
- No provider, bundle or skill abstraction is introduced.

## Validation debt

The immediate P1.3 HARD gates are cleared at
`49bdac1f732acaaee3154ed60baffd675130991a`:

- `P1-REAL-VERSION`: **PASS**;
- `P1-REAL-SOAK-100`: **PASS**.

P1.4 creates no new real-environment debt.

Phase 1 completion debt that remains open independently:

- `P1-REAL-TOOLCALL` — HARD before Phase 1 completion;
- `P1-REAL-CANCEL` — HARD before Phase 1 completion.

## Exact next action

Select P1.5 as the remaining conformance repair: classify Codex overload/backpressure as retryable
only when host effect state is safe. Reuse the bounded provider category retained by P1.4; do not
retry capability calls or writes merely because the provider reports overload. Add focused
deterministic regressions, reassess real-environment debt for the retryability contract, and keep
Phase 1 `IN_PROGRESS` until the conformance matrix is green plus `P1-REAL-TOOLCALL` and
`P1-REAL-CANCEL` pass.
