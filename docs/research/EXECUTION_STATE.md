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
active_slice: P1.5-overload-backpressure-classification
active_slice_state: COMPLETE
current_gate_type: HARD_REAL_ENV
blocking_validations: P1-REAL-TOOLCALL, P1-REAL-CANCEL
phase_completion_validations: P1-REAL-TOOLCALL, P1-REAL-CANCEL
next_slice: NONE_UNTIL_PHASE1_REAL_ENV_VALIDATION
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

This run reconstructed remote `main` at `bc26a894324d9404d66bc2dacba433d67dea2336` before writing.
No newer commit, failed validation, regression report or handoff appeared after P1.4, so the exact
READY slice remained P1.5.

Previously committed Phase 1 real-environment evidence remains:

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
Odoo             | 18.0 Community
Codex            | 0.149.1
selected Odoo regression battery | 46 tests, 0 failures/errors
soak             | 100/100 turns, 0 protocol/provider/authority/binding failures
```

Those passes cover the P1.3 compatibility checkpoint and are retained as historical evidence. They
do not satisfy the independent Phase 1 completion gates for tool mapping and cancellation on the
final provider checkpoint.

## P1.4 retained provider-failure contract

P1.4 preserved only bounded terminal provider facts on `CodexDecisionError`:

- provider category from `codexErrorInfo`;
- optional HTTP status in 100-599;
- optional bounded upstream machine code;
- no raw provider message, `additionalDetails`, prompt, credentials, request body, stdout/stderr or
  unrestricted provider payload.

`invalid_json_schema` continues to map to `codex_output_schema_invalid`; other terminal provider
failures keep the current sanitized `codex_turn_failed` product code.

## P1.5 implementation

P1.5 closes the remaining static `overload_backpressure` conformance gap without adding an automatic
retry loop.

`CodexDecisionError` now exposes a separate advisory `provider_retryable` boolean. The classifier is
intentionally narrow:

```text
provider category == serverOverloaded
AND host_effect_safe == True
    -> provider_retryable = True
otherwise
    -> provider_retryable = False
```

The one-decision Codex adapter marks its two terminal provider routes `host_effect_safe=True` because
that adapter has no capability executor and cannot itself produce an Odoo business effect. The
classifier does not infer retryability from a generic HTTP 503, `httpConnectionFailed`,
`usageLimitExceeded`, schema errors or unknown categories. Calling the same classifier with
`host_effect_safe=False` suppresses retryability even for `serverOverloaded`.

This flag is metadata only in P1.5. It does not retry a provider request, replay a reasoning
capability, re-run a PLAN handler, cross the write barrier or change recovery semantics. The later
host-owned failure contract may consume this fact only together with authoritative effect state.

## Tests added or updated

```text
addons/odoo_ai_assistant/runtime/agent/codex_decision.py
tests/contracts/current_codex_decision_conformance.py
tests/unit/test_codex_provider_conformance.py
tests/unit/test_codex_terminal_failure_projection.py
docs/CURRENT_STATE.md
docs/UNIFIED_AGENT_RUNTIME.md
docs/research/PHASE1_PROVIDER_BOUNDARY.md
docs/research/EXECUTION_STATE.md
```

The P1.5 regression coverage checks:

- `serverOverloaded` is retryable at the explicit effect-safe provider boundary;
- the same category is not retryable when effect state is unsafe;
- generic transport HTTP 503 is not treated as overload;
- usage-limit and schema failures remain outside this narrow backpressure classifier;
- P1.4 bounded redaction and schema-error mapping remain intact;
- the dependency-light conformance binding expects 14/14 cases after P1.5.

## Tests actually executed

The current ChatGPT execution environment ran a focused extracted classifier harness against the
same P1.5 logic prepared for publication:

```text
serverOverloaded + host_effect_safe=True  -> provider_retryable=True
serverOverloaded + host_effect_safe=False -> provider_retryable=False
httpConnectionFailed + HTTP 503           -> provider_retryable=False
usageLimitExceeded                         -> provider_retryable=False
invalid_json_schema                        -> provider_retryable=False
result: PASS
```

The immediately preceding preparation run also executed the dependency-light P1.5 test snapshot
before publication was interrupted: six terminal/backpressure regressions passed; seven
provider-conformance tests passed with the complete-checkout matrix deselected; Python compilation
passed. Those results are supporting preparation evidence, not a substitute for the still-unrun full
repository/Odoo gates.

## Tests not executed

```text
complete tests/unit/test_codex_provider_conformance.py matrix in a full repository checkout
full unit suite
dependency-light E2E convergence suite
Odoo addon/module-update suites
P1-REAL-TOOLCALL
P1-REAL-CANCEL
```

No GitHub Actions were used.

## Static conformance expectation

After P1.5 the dependency-light source binding is expected to report:

```text
14 PASS / 0 FAIL
```

P1.5 does not by itself close Phase 1 because the final checkpoint still requires the real host/tool
mapping and cancellation evidence below.

## Validation debt

Cleared historical Phase 1 evidence:

```text
P1-REAL-SOAK-100 | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
P1-REAL-VERSION  | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
```

Open Phase 1 completion debt on the final P1.5 checkpoint (`THIS_COMMIT`):

```text
P1-REAL-TOOLCALL | HARD | prove host/provider capability mapping under effective user | blocks Phase 2
P1-REAL-CANCEL   | HARD | prove cancellation binds to intended active provider turn | blocks Phase 2
```

P1.5 creates no new mandatory validation ID because it adds advisory classification metadata and no
automatic retry/effect behavior.

## Exact next action

Do not select a Phase 2 implementation slice yet. Install/update the addon from the exact P1.5
checkpoint represented by this commit and run `P1-REAL-TOOLCALL` plus `P1-REAL-CANCEL` exactly as
defined in `REAL_ENV_VALIDATION_PROTOCOL.md`. Commit sanitized PASS/FAIL evidence. If either gate
fails, select the smallest Phase 1 repair; if both pass and the deterministic conformance matrix is
green, close Phase 1 and make the first Phase 2 failure-contract slice READY.
