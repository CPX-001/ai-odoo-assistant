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
active_slice: P1.4-terminal-failure-preservation
active_slice_state: COMPLETE
current_gate_type: NONE
blocking_validations: NONE_FOR_NEXT_SLICE
phase_completion_validations: P1-REAL-TOOLCALL, P1-REAL-CANCEL
next_slice: P1.5-overload-backpressure-classification
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

The run reconstructed `main` at `035cc801fc9b0de6c401837274d4b6054c34c3d6` and processed the
newly committed P1.3 real-environment evidence before selecting more provider work.

The installed Odoo instance had been explicitly updated from exact checkpoint
`49bdac1f732acaaee3154ed60baffd675130991a`. The selected Odoo regression battery passed 46 test
methods with zero failures/errors. `P1-REAL-VERSION` passed on Odoo 18.0 Community with Codex
0.149.1 and an authenticated provider-owned account under Odoo's `data_dir`.

`P1-REAL-SOAK-100` passed 100/100 normal product-path turns: 80 greetings and 20 simple reads,
with zero protocol-shape failures, provider-process failures, runtime-unavailable retries,
host-authority bypasses, wrong-turn/call bindings or read tool-boundary failures. Median latency was
7818.479 ms and p95 was 34563.910 ms. Six bounded `field_not_in_schema` corrections completed
normally and were not classified as provider failures. Sanitized evidence is recorded in
`docs/research/evidence/phase1/2026-08-27/P1-REAL-VERSION-SOAK-49bdac1.md`.

No newer failed validation, regression report or handoff was present on `main`, so P1.4 remained the
first READY repair.

## P1.3 implementation

P1.3 repairs only the active one-decision adapter's additive-notification compatibility boundary.
The shared legacy Codex protocol validator remains strict; `CodexDecisionEngine` wraps it with a
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
adapter or capability/action behavior was included in P1.3.

## P1.4 implementation

P1.4 closes only the `terminal_failure` conformance gap while deliberately leaving
`overload_backpressure` unresolved.

`CodexDecisionEngine` now preserves a bounded `CodexProviderFailure` on terminal decision-adapter
exceptions. The preserved projection contains only:

- a bounded ASCII provider category derived from `codexErrorInfo`;
- an optional HTTP status in the normal 100-599 range;
- an optional bounded upstream machine code parsed from a bounded JSON provider message.

Raw provider message text, `additionalDetails`, request bodies, prompts, stdout/stderr, credentials
and unrestricted payloads are not retained on the exception. Invalid or unbounded structured fields
are discarded rather than copied through. The existing specific
`codex_output_schema_invalid` mapping remains intact when the upstream machine code is
`invalid_json_schema`; other terminal failures still keep the existing sanitized product code
`codex_turn_failed`.

The same projection is used for both non-retrying top-level `error` notifications and failed
`turn/completed` events. `serverOverloaded` may now survive as a provider fact, but P1.4 does not
mark it retryable and does not introduce automatic retries; that remains P1.5.

This is intentionally not the Phase 2 `FailureEnvelope`/browser taxonomy. P1.4 retains provider
facts at the adapter boundary so the next failure-contract phase does not have to recover
information that was already destroyed.

## Tests added or updated

- `tests/contracts/current_codex_decision_conformance.py` now recognizes bounded structured terminal
  error preservation and moves `terminal_failure` to conformant;
- `tests/unit/test_codex_provider_conformance.py` updates the expected current projection from 12/14
  to 13/14, leaving only `overload_backpressure`;
- `tests/unit/test_codex_terminal_failure_projection.py` adds dependency-light executable regressions
  for bounded provider facts, raw-message redaction, invalid-field discard, both terminal routes and
  deliberate non-classification of overload retryability.

## Tests actually executed

The available ChatGPT execution sandbox ran the new dependency-light regression against the exact
modified source snapshot prepared for publication:

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

The focused binding reports `terminal_failure` with
`structured_error_preserved = true`. No Odoo runtime, Codex process or GitHub Actions were used for
these checks.

The expected static conformance projection after P1.4 is 13/14. Only
`overload_backpressure` remains intentionally non-conformant.

## Tests not executed

```text
full tests/unit/test_codex_provider_conformance.py matrix in a repository checkout
full tests/unit suite
dependency-light E2E convergence suite
Odoo addon/module-update suites
P1-REAL-TOOLCALL
P1-REAL-CANCEL
```

These were not available through the connected GitHub interface and are not claimed as passed.
P1.4 adds no new mandatory real-environment gate because it changes only the bounded provider fact
projection, not host effects, retry policy or browser failure semantics. Real failure-family
presentation remains Phase 2 validation work.

## Validation debt

P1.3 debt remains cleared:

```text
P1-REAL-SOAK-100 | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
P1-REAL-VERSION  | HARD | PASS | 49bdac1f732acaaee3154ed60baffd675130991a
```

Independent Phase 1 completion debt remains open:

```text
P1-REAL-TOOLCALL | HARD | host/provider capability mapping | Phase 2+
P1-REAL-CANCEL   | HARD | provider turn identity/cancellation | Phase 2+
```

P1.4 creates no additional real-environment debt. It does not classify failures as retryable,
alter cancellation or execute any capability/action.

## Exact next action

Select P1.5 as the final currently observed provider-conformance repair: classify Codex
overload/backpressure as retryable only when host effect state is safe, without introducing blind
retry of capability or write effects. Preserve the P1.4 bounded provider facts as input, add focused
deterministic regression coverage, and reassess whether P1.5 creates a new HARD real-environment
gate. Do not mark Phase 1 complete until the conformance matrix is green and
`P1-REAL-TOOLCALL` plus `P1-REAL-CANCEL` pass.
