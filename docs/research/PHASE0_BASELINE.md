# Phase 0 reproducible baseline

Research/playbook source: `FOUNDATION_STABILIZATION_PLAYBOOK.md`  
Phase started from main: `3f175cdc9b38aa3fc5aac4f231c0aee5d86b46ef`  
Latest real ACTION checkpoint materially tested: `38c7c9a121cc797b9a2737fb312283506aa152f6`<br>
Target: Odoo 18 Community / embedded runtime / Codex primary  
Status: **blocked — real ACTION produced a completed zero-step plan with no approval preview**

## Purpose

Phase 0 exists to stop debugging latency and failures by impression. It must produce repeatable
scenarios and enough timing/error evidence to attribute a slow or failed turn before any
provider-lifecycle, streaming, UI, or latency architecture is changed.

This document is an execution record, not current-state architecture authority. Current code,
accepted ADRs and the documents indexed by `docs/README.md` remain authoritative.

## Implemented in this phase

### 1. Machine-readable scenario matrix

`tests/e2e/embedded_phase0_scenarios.json` defines the permanent baseline scenarios required by the
stabilization playbook:

- `hello`;
- `read_partner`;
- `query_sales`;
- `aggregate_sales`;
- `write_preview`;
- `write_execute_verify`;
- `acl_denied`;
- `provider_auth_missing`;
- `provider_process_missing`;
- `provider_disconnect`;
- `provider_timeout`;
- `tool_invalid_input`;
- `tool_handler_failure`;
- `invalid_final_output`;
- `cancel_queued`;
- `cancel_running`;
- `worker_restart_before_write`;
- `worker_loss_after_write_barrier`.

The catalog is format version 2. Each scenario records:

```text
entrypoint
requires
expected.kind
expected.states
expected.error_codes
```

This matters because the current product does not persist every failure as a turn.

#### Current-code correction to the original playbook assumptions

Inspection of `controllers/turn_runtime.py` and `services/runtime_account.py` showed that the runtime
account gate runs before `enqueue_for_current_user()`.

Therefore:

```text
provider_auth_missing
  -> /odoo_ai/v1/turn returns codex_not_connected
  -> no odoo.ai.turn exists

provider_process_missing
  -> /odoo_ai/v1/turn returns codex_unavailable
  -> no odoo.ai.turn exists
```

The earlier scenario catalog incorrectly expected both cases to reach persisted `failed` turns.
Format v2 records them as `request_error` outcomes instead of inventing a turn state that current
code does not produce.

A deterministic unit test locks this distinction to the current source of truth.

### 2. Browser monotonic timing checkpoints

`streamAssistantChat()` has optional `onTiming` and `nowCall` diagnostic hooks. The normal product
caller can ignore them.

Current client checkpoints:

```text
submit_received
turn_persisted
browser_first_activity
browser_final
```

`nowCall` defaults to `performance.now()` with a `Date.now()` fallback. Tests inject a deterministic
clock. The callback receives only checkpoint name, elapsed milliseconds and minimal turn/state
metadata.

Important: the current `onDelta` path is still progress labels derived from polling. Therefore
Phase 0 does **not** record `browser_first_answer_delta`, because doing so would falsely label
progress text as assistant answer streaming.

### 3. Codex provider monotonic checkpoints

`CodexReasoningEngine` creates one best-effort, content-free monotonic recorder per provider run.
It emits sanitized `diagnostic.timing` events through the existing `CapabilityContext` event sink.

Current provider checkpoints:

```text
runtime_started
provider_process_started
provider_initialized
provider_thread_started
provider_turn_started
first_provider_event
first_answer_delta
```

`first_answer_delta` is timing-only. The adapter notices the already-allowed
`item/agentMessage/delta` notification method but does not persist or forward its text. This
deliberately does **not** implement product answer streaming ahead of Phase 4.

The diagnostic event payload is limited to:

```json
{"point": "provider_initialized", "elapsed_ms": 123.456}
```

The recorder is idempotent per point and best-effort: a failure to persist diagnostic timing must
not fail a product turn. No raw provider notification, prompt, output, tool arguments,
stdout/stderr or credential data is added.

### 4. Baseline trace summarizer

`tests/e2e/phase0_baseline.py` consumes a captured trace and combines:

- client monotonic checkpoints;
- persisted Odoo turn-event timestamps;
- provider `diagnostic.timing` events;
- final state/error codes;
- optional model-turn/tool-call/token counters.

Clock domains are kept explicit. `timings_ms` is a submit-relative product timeline. Provider
process-local monotonic offsets remain separate so the summarizer does not pretend browser and
cron workers share one monotonic clock.

Current evidence mappings are intentionally explicit:

| Phase 0 point | Current evidence |
| --- | --- |
| `turn_persisted` | client monotonic timing + `queued` event |
| `worker_claimed` | `started` event |
| `runtime_started` | `reasoning.started` wall-clock proxy + `diagnostic.timing` |
| provider lifecycle points | `diagnostic.timing` event timestamp + runtime monotonic offset |
| `first_answer_delta` | timing-only `diagnostic.timing`; answer text is not persisted |
| `first_capability_started` | first `tool.started` event |
| `last_capability_completed` | last `tool.completed` / `tool.failed` event |
| `reasoning_completed` | `reasoning.completed` event |
| `result_persisted` | first terminal/approval event after authoritative persistence |
| browser points | client `onTiming` |

The summarizer reports required-but-missing checkpoints instead of fabricating values. It also
preserves `capture_kind`, `expectation_met`, `request_error_code` and the derived `outcome_kind` so
a saved summary retains enough provenance for the aggregate exit-gate evaluator.

### 5. Live Odoo HTTP capture runner

`tests/e2e/phase0_live_capture.py` is the current bridge from the Phase 0 contract to a real Odoo
instance.

It:

1. authenticates with a normal Odoo web session;
2. calls the product `/odoo_ai/v1/turn` route;
3. polls `/odoo_ai/v1/turn/status` when a turn was actually persisted;
4. records product/browser elapsed timing;
5. stores only the event fields needed for baseline analysis;
6. preserves `diagnostic.timing` only as `{point, elapsed_ms}`;
7. records a pre-enqueue `request_error_code` when the product gate rejects the request;
8. validates the observed result against the scenario catalog.

P0.1 extended the capture contract without changing product runtime behavior:

- once enqueue has persisted a turn, polling timeout, Odoo HTTP/RPC failure, invalid status or a
  turn-id mismatch returns a sanitized partial trace instead of discarding prior evidence;
- capture-side failures use `capture_error_code`, remain `expectation_met=false` and retain already
  observed snapshots plus available browser timings;
- successful `completed` or `awaiting_confirmation` turns do not promote a diagnostic code from a
  recovered attempt to terminal `original_error_code`.

The trace deliberately excludes:

```text
database password
message text
screen context
assistant answer
plan/preview payloads
general event payloads
raw tool/provider data
stdout/stderr
credentials
```

Plain HTTP is refused for non-loopback hosts. This prevents the capture helper from casually
sending Odoo credentials to a remote clear-text endpoint.

The runner builds a complete generic Odoo screen hint when `ODOO_AI_PHASE0_SCREEN_JSON` is omitted.
When a screen JSON fixture is supplied, only the current bounded screen keys are accepted and the
runner always replaces `captured_at` with the actual submission time. This avoids an otherwise easy
failure mode where a saved screen fixture is rejected as expired by the current five-minute Odoo
screen-context bound.

The runner currently supports `entrypoint=enqueue`. Plan-decision, cancellation and synthetic
recovery fixtures remain explicit later extensions; they are not silently emulated.

Run example:

```bash
export ODOO_AI_PHASE0_DB=odoo
export ODOO_AI_PHASE0_LOGIN=admin
export ODOO_AI_PHASE0_PASSWORD='...'
export ODOO_AI_PHASE0_MESSAGE='Hola'

python tests/e2e/phase0_live_capture.py \
  --scenario hello \
  --out /tmp/phase0/hello-001.json
```

For a screen-specific trial, `ODOO_AI_PHASE0_SCREEN_JSON` is optional input such as:

```json
{"model":"res.partner","view_type":"list"}
```

The runner fills missing bounded screen fields and stamps a fresh `captured_at` before submission.

`ui_error_code` is intentionally not inferred from backend state. For a failure capture,
`--ui-error-code` or `ODOO_AI_PHASE0_UI_ERROR_CODE` should be supplied only after the final
browser/product code has actually been observed.

### 6. Phase 0 aggregate report / gate evaluator

`tests/e2e/phase0_report.py` accepts raw captures or already summarized traces and reports:

- number of valid live captures;
- minimum matrix coverage;
- provider/tool/full-turn timing decomposition;
- `hello` and simple-read latency distributions;
- observed original-vs-UI failure pairs;
- number of distinct failure paths represented by those pairs;
- each Phase 0 exit-gate boolean;
- final `ready_for_phase1`.

The timing-decomposition gate is deliberately stricter than two independent booleans: one
successful read/action turn must contain queue, provider, tool and finalization points together.
Likewise, five repeated captures of the same failure cannot satisfy the five-failure-path gate;
five distinct scenario paths are required.

The command exits with status `0` only when the documented gate is satisfied. Incomplete evidence
returns status `2`; it cannot make Phase 1 appear ready simply because deterministic unit tests
passed.

Example:

```bash
python tests/e2e/phase0_report.py /tmp/phase0/*.json \
  --out /tmp/phase0/report.json
```

## Trace contract

A normal persisted-turn capture has this shape:

```json
{
  "format_version": 1,
  "capture_kind": "live_http",
  "scenario_id": "hello",
  "timings": [
    {"point": "submit_received", "elapsed_ms": 0},
    {"point": "turn_persisted", "elapsed_ms": 24.3},
    {"point": "browser_first_activity", "elapsed_ms": 25.1},
    {"point": "browser_final", "elapsed_ms": 10342.8}
  ],
  "status_snapshots": [
    {"state": "queued", "error_code": null, "events": []},
    {"state": "completed", "error_code": null, "events": []}
  ],
  "request_error_code": null,
  "capture_error_code": null,
  "original_error_code": null,
  "ui_error_code": null,
  "expectation_met": true
}
```

An interrupted persisted-turn capture uses the same bounded shape, preserves the snapshots and
timings already observed, sets `capture_error_code` to the normalized capture-side failure,
`expectation_met=false`, and leaves `original_error_code=null` because no terminal product error was
observed.

A pre-enqueue provider gate failure contains no invented turn:

```json
{
  "capture_kind": "live_http",
  "scenario_id": "provider_auth_missing",
  "status_snapshots": [],
  "request_error_code": "codex_not_connected",
  "original_error_code": "codex_not_connected",
  "ui_error_code": null,
  "expectation_met": true
}
```

Do not put message text, prompts, raw tool arguments/results, auth data, stdout/stderr or provider
secrets in baseline traces.

Run the one-trace summarizer with:

```bash
python tests/e2e/phase0_baseline.py /path/to/trace.json
```

## Required checkpoints and current coverage

The playbook requires:

```text
submit_received                 covered client-side
turn_persisted                  covered client-side + queued event
worker_claimed                  covered by started event
runtime_started                 covered by reasoning.started + diagnostic.timing
provider_process_started        covered by diagnostic.timing
provider_initialized            covered by diagnostic.timing
provider_thread_started         covered by diagnostic.timing
provider_turn_started           covered by diagnostic.timing
first_provider_event            covered by diagnostic.timing
first_answer_delta              covered timing-only when Codex emits agentMessage/delta
first_capability_started        covered by tool.started
last_capability_completed       covered by tool.completed/tool.failed
reasoning_completed             covered by reasoning.completed
result_persisted                covered by terminal/approval event
browser_first_activity          covered client-side
browser_first_answer_delta      MISSING by design until real answer streaming exists
browser_final                   covered client-side
```

The intentionally missing browser answer-delta checkpoint belongs to the later real-streaming
phase. Phase 0 can still measure whether Codex produced a delta and how long it took.

## Error-pair capture

For failure scenarios the baseline must retain two values side by side:

```text
original_error_code
ui_error_code
```

The first is the most specific sanitized code observed before presentation flattening. The second
is what the browser/product finally exposes. This is measurement only; changing the failure
taxonomy belongs to the later failure-contract phase.

At least these five failure families must be captured before Phase 0 closes:

1. provider auth missing;
2. provider process missing;
3. provider disconnect/EOF;
4. provider timeout;
5. invalid capability/provider output.

The first two are currently pre-enqueue request failures, not persisted failed turns.

Additional recommended pairs: ACL denied, cancellation and write-recovery-required.

## Trial protocol

For each scenario:

1. reset/verify the named fixture requirements;
2. capture the Odoo HTTP product path or the explicit scenario entrypoint;
3. record final state or pre-enqueue request error;
4. preserve the most specific sanitized original code available;
5. observe and add the final UI error code for failure-pair trials;
6. run `phase0_baseline.py` and/or `phase0_report.py`;
7. retain sanitized traces/summaries, not raw prompts/tool payloads.

For latency distributions, run `hello` and one simple read repeatedly. Do not use a single warm run
as evidence. The Phase 1 gate later requires at least 100 repeated simple turns without
protocol-shape failures.

## Deterministic verification for this tooling

The current standalone Phase 0 tooling has deterministic tests for:

- scenario catalog completeness and outcome semantics;
- the two current pre-enqueue provider gate failures;
- live-capture redaction;
- fresh/complete generic screen capture and rejection of unexpected screen keys;
- timing capture;
- request-error capture;
- refusal of remote plain HTTP credentials;
- raw-capture to saved-summary provenance preservation;
- one-turn timing-decomposition gate semantics;
- distinct failure-path counting;
- refusal to close the failure-pair gate without observed UI codes.

These tests validate the measurement tooling. They do **not** substitute for the live exit gate.

## Phase 0 exit gate

Current status:

- [ ] `hello`, one read, one action and one failure have live reproducible captures in a real
  embedded Odoo + authenticated Codex environment.
- [x] A live turn has been decomposed into queue/provider/tool/finalization timing using the
  implemented checkpoints.
- [x] The simple-turn latency has been attributed from measured live data rather than guessed.
- [x] At least five important failure paths have original code + final UI code recorded side by
  side.

The repository now has the scenario contract, client/provider instrumentation, redacted live
capture runner, summarizer and aggregate gate evaluator needed for those measurements. The gate
remains open only because the safe disposable ACTION baseline has not yet been rerun.

## Next work inside Phase 0

Stay in Phase 0. Do **not** begin the provider-boundary refactor yet.

Next:

1. prepare one disposable partner for a reversible update;
2. rerun `P0-REAL-ACTION` through preview, explicit browser approval and verification;
3. restore the disposable fixture after capturing the authoritative result;
4. rerun `phase0_report.py`;
5. only then let the aggregate report decide whether Phase 1 may start.

## Live validation run — 2026-08-27

The first real Odoo 18 + Codex 0.149.1 run tested
`8641b013e62018d8d47cfb2a44106ff039b84aca` after explicitly restarting Odoo. Sanitized captures
and the full diagnosis are stored under `docs/research/evidence/phase0/2026-08-27/`.

Observed result:

- `P0-REAL-HELLO`: four completed turns from five submitted; completed p50 8,436.853 ms and range
  6,726.211–18,171.923 ms;
- `P0-REAL-READ`: **FAIL** despite a `completed` state; no tool evidence and the browser answer said
  the Odoo query failed;
- `P0-REAL-ACTION`: **FAIL**; no preview, Odoo restarted during the turn, the turn was cancelled with
  `write_barrier=false`, and the fixture was unchanged;
- one current-HEAD failure pair was completed (`codex_unavailable` → `codex_unavailable`);
- `phase0_report.py`: `ready_for_phase1=false`.

The run also found that failed-attempt timing events roll back, a recovered successful turn retains
a stale transient `original_error_code`, and a transport exception prevents the live runner from
writing partial evidence. Phase 0 remains open.

## P0.1 corrective validation — 2026-08-27

P0.1 was materially validated at `121108e55ef0ff91adb0377920f73128875536ac`.

- deterministic runner regression: **PASS**, 7 tests;
- `phase0_live_capture.py` compilation: **PASS**;
- `P0.1-REAL-PARTIAL-CAPTURE`: **PASS** against real Odoo 18 using a loopback-only controlled
  interruption after authentication and real turn persistence;
- saved evidence retained one queued snapshot and submit/persist/activity/final timings, reported
  `capture_error_code=odoo_http_unavailable`, kept `expectation_met=false`, and contained no prompt,
  answer, password, tool/provider payload or terminal `original_error_code`;
- a non-injected real `hello` did not recover: it ended `failed` after three
  `runtime_unavailable` diagnostics, so real recovered-retry attribution remains not observed while
  its deterministic regression is PASS.

The P0.1 local and real validation debts are closed. At that checkpoint, READ, ACTION, timing
decomposition and the required failure-pair matrix remained incomplete, so the next normal slice
was `P0.2-read-failure-diagnosis` and ACTION remained frozen.

## P0.2 corrective validation — 2026-08-27

P0.2 was materially validated at `a05e75006f53b056f31ab96c3864092d89199480` after updating the
addon and restarting Odoo 18 in an adapted disposable local environment using Codex CLI 0.144.2.

- deterministic READ acceptance regression: **PASS**, 3 tests;
- capture and acceptance scripts: **PASS** compilation;
- historical false-positive capture: correctly rejected with exit `2` and both tool events missing;
- `P0-REAL-READ`: **PASS** with final `completed`, two tool start/completion pairs and machine
  `accepted=true`;
- authenticated browser-history payload: exact fixture name/email matched the actual Odoo partner;
- queue/provider/tool/finalization evidence captured; browser final 16,120.006 ms;
- Odoo remained active with zero service restarts during the READ.

Sanitized artifacts and the full evidence record are under
`docs/research/evidence/phase0/2026-08-27/`. P0.2 and `VD-P0.2-REAL-READ` are closed. Phase 0 remains
open: P0.3 must bound the provider/Odoo crash path before ACTION is retried, and the failure-pair
matrix still requires additional distinct paths.

## P0.3 and P0.4 corrective validation — 2026-08-27

P0.3 passed at `c114f15`: three greetings and one capability-backed read completed without an
Odoo restart, unhealthy service state or signal-5 observation.

P0.4 passed at `9008821` in real Odoo and Chrome. EOF, bounded timeout and invalid final output
ended `failed` with their manifest codes; the browser flattened all three to
`service_unavailable`. The database-scoped auth gate was also observed as
`codex_not_connected -> codex_not_connected`. Together with `provider_process_missing`, the
aggregate report counts five distinct original/UI pairs.

`phase0_report.py` now passes the timing, latency-attribution and five-failure-pair gates. It exits
`2` only because `minimum_live_matrix.action=false`. The exact next gate is the safe disposable
ACTION rerun; Phase 1 remains locked.
