# Phase 1 — provider boundary stabilization

Date: 2026-08-27
Inspected implementation/test base: `bc26a894324d9404d66bc2dacba433d67dea2336`
Final live-tested checkpoint: `db6e5c12c53e9a99ad3a55f7472eb13f93855a06`
Status: `COMPLETE`

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
source and exercises benign tolerance, malformed rejection, identity mismatch rejection,
unverified `callId` rejection and propagation of known critical-event failures.

The first repository-capable execution exposed a false negative inherited from the P1.2 static
binding for `final_answer_mapping`. Checkpoint `012e9c8888011e70d8029d18f028a155f1d5a868`
repaired the harness so it inspects the adapter delegation plus the shared parser branch rather than
a prompt literal. No runtime behavior changed in that correction.

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

Six reads required the existing bounded `field_not_in_schema` correction and then completed. The
sanitized evidence is
`docs/research/evidence/phase1/2026-08-27/P1-REAL-VERSION-SOAK-49bdac1.md`.

## P1.4 — bounded terminal-failure preservation

State: `COMPLETE`

Objective:

- close only the `terminal_failure` conformance gap;
- preserve machine-readable provider terminal facts across the Codex decision adapter boundary;
- never preserve raw provider messages or `additionalDetails`;
- retain current host/product error codes and leave retry/backpressure semantics for a separate slice.

Implementation:

- terminal decision failures raise `CodexDecisionError`, a `CodexAgentError` subtype carrying an
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

`serverOverloaded` became preservable as a provider category but was deliberately not classified
retryable until P1.5.

## P1.4 deterministic/eval coverage

Added or updated:

```text
addons/odoo_ai_assistant/runtime/agent/codex_decision.py
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
tests/unit/test_codex_terminal_failure_projection.py
```

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

Static contract projection after P1.4:

```text
13 PASS / 1 FAIL
remaining: overload_backpressure
```

P1.4 added no mandatory real-environment validation ID because it changed only bounded provider
fact preservation, not host effects, retry policy, cancellation or browser failure presentation.

## P1.5 — overload/backpressure classification

State: `COMPLETE`

Objective:

- close the final `overload_backpressure` conformance gap;
- classify only explicit Codex `serverOverloaded` terminal facts as provider-retryable;
- make retryability conditional on an explicitly effect-safe provider boundary;
- do not introduce provider-loop retries, capability retries, write retries or Phase 2 browser
  failure semantics.

Implementation:

- `CodexDecisionError` now carries `provider_retryable`, an advisory host-facing boolean separate
  from the bounded provider facts in `CodexProviderFailure`;
- `_RETRYABLE_PROVIDER_CATEGORIES` contains only the explicit `serverOverloaded` category observed
  at the Codex boundary;
- `_provider_failure_is_backpressure()` classifies by provider category, not by generic HTTP status;
- both current terminal paths call `_decision_terminal_error(..., host_effect_safe=True)` because
  the one-decision adapter has no capability executor and cannot create an Odoo business effect;
- `_decision_terminal_error()` sets the advisory flag only when both the explicit overload category
  and `host_effect_safe=True` are present;
- a generic HTTP 503, `httpConnectionFailed`, `usageLimitExceeded`, schema failure or unknown
  terminal category is not promoted to retryable backpressure;
- passing `host_effect_safe=False` suppresses retryability even for `serverOverloaded`;
- no retry loop consumes this flag in P1.5. Existing host persistence, interrupted-call handling,
  write barrier and recovery semantics remain unchanged.

The classification is deliberately narrower than the eventual Phase 2 failure/retry contract. P1.5
preserves enough structured information for the later host layer without declaring ambiguous
effects safe or encouraging a blind repeat.

## P1.5 deterministic/eval coverage

Added or updated:

```text
addons/odoo_ai_assistant/runtime/agent/codex_decision.py
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
tests/unit/test_codex_terminal_failure_projection.py
docs/CURRENT_STATE.md
docs/UNIFIED_AGENT_RUNTIME.md
```

Focused dependency-light coverage verifies:

- explicit `serverOverloaded` + effect-safe boundary => `provider_retryable=True`;
- the same provider fact with unsafe/unknown effect state => retryability suppressed;
- generic HTTP 503 / transport failure is not enough to infer backpressure;
- usage-limit and schema failures remain non-retryable under this narrow classifier;
- raw provider message/detail redaction from P1.4 remains intact;
- the static conformance projection is expected to be 14/14 with no failed cases.

Available ChatGPT execution for the prepared P1.5 source ran the focused terminal/backpressure
regression, the dependency-light provider-conformance tests that do not require a complete checkout,
and Python compilation. The complete repository, Odoo addon/module-update and real Odoo+Codex gates
remain separately tracked in `EXECUTION_STATE.md` and are not claimed as passed here.

P1.5 created no new real-environment validation ID because it introduced classification metadata
only and no automatic retry/effect behavior. The existing `P1-REAL-TOOLCALL` and
`P1-REAL-CANCEL` HARD completion gates subsequently passed against the final checkpoint, as
recorded below.

## Invariants

- Odoo remains operational and persistence authority.
- Effective-user capability execution remains `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider output is untrusted and host-validated.
- PLAN remains proposal-only before the existing action lifecycle.
- Unknown server requests remain rejected; notification tolerance grants no host authority.
- Preserved provider failure facts and `provider_retryable` are diagnostic/advisory data only.
- Raw provider messages/details are not retained by the provider projection.
- P1.5 performs no automatic provider, capability or write retry.
- A retryability hint is false whenever the caller does not explicitly mark the provider boundary
  effect-safe.
- The durable write barrier and recovery-required behavior remain authoritative for ambiguous
  effects.
- No SQL/Python/shell/sudo/unrestricted ORM escape hatch is introduced.
- Codex credentials remain provider-owned.
- No provider, bundle or skill abstraction is introduced.

## Validation debt

Cleared evidence retained from P1.3:

- `P1-REAL-VERSION`: **PASS** at `49bdac1f732acaaee3154ed60baffd675130991a`;
- `P1-REAL-SOAK-100`: **PASS** at `49bdac1f732acaaee3154ed60baffd675130991a`.

P1.4 and P1.5 create no additional mandatory real-environment gate.

Final completion evidence:

- `P1-REAL-TOOLCALL`: **PASS** at `db6e5c12c53e9a99ad3a55f7472eb13f93855a06`;
- `P1-REAL-CANCEL`: **PASS** at `db6e5c12c53e9a99ad3a55f7472eb13f93855a06`;
- complete addon install/update battery: **PASS**, 0 failed / 0 errors;
- dependency-light provider/unit/E2E matrices: **PASS**.

The sanitized close-out evidence is
`docs/research/evidence/phase1/2026-08-27/P1-REAL-TOOLCALL-CANCEL-db6e5c1.md`.
No mandatory Phase 1 validation debt remains.

## Exact next action

Phase 1 is closed. Reconstruct Phase 2 from `EXECUTION_STATE.md`, create its atomic phase/slice
record, and start with the structured `FailureEnvelope` contract. Do not mix public-activity,
answer-streaming or chat-UX work into that first failure-contract slice.
