# Phase 0 reproducible baseline

Research/playbook source: `FOUNDATION_STABILIZATION_PLAYBOOK.md`  
Phase started from main: `3f175cdc9b38aa3fc5aac4f231c0aee5d86b46ef`  
Latest implementation slice inspected from: `9840ef4299452c2bed253d85f3453547622a57e3`  
Target: Odoo 18 Community / embedded runtime / Codex primary  
Status: **in progress — measurement + live-capture tooling implemented, live exit gate not yet satisfied**

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

The catalog is now format version 2. Each scenario records:

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

The summarizer reports required-but-missing checkpoints instead of fabricating values.

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

The runner currently supports `entrypoint=enqueue`. Plan-decision, cancellation and synthetic
recovery fixtures remain explicit later extensions; they are not silently emulated.

Run example:

```bash
export ODOO_AI_PHASE0_DB=odoo
export ODOO_AI_PHASE0_LOGIN=admin
export ODOO_AI_PHASE0_PASSWORD='...'
export ODOO_AI_PHASE0_MESSAGE='Hola'
export ODOO_AI_PHASE0_SCREEN_JSON='{"model":null,"view_type":null}'

python tests/e2e/phase0_live_capture.py \
  --scenario hello \
  --out /tmp/phase0/hello-001.json
```

`ui_error_code` is intentionally not inferred from backend state. For a failure capture,
`--ui-error-code` or `ODOO_AI_PHASE0_UI_ERROR_CODE` should be supplied only after the final
browser/product code has actually been observed.

### 6. Phase 0 aggregate report / gate evaluator

`tests/e2e/phase0_report.py` accepts raw captures or already summarized traces and reports:

- number of valid live captures;
- minimum matrix coverage;
- provider and tool timing decomposition;
- `hello` and simple-read latency distributions;
- observed original-vs-UI failure pairs;
- each Phase 0 exit-gate boolean;
- final `ready_for_phase1`.

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
  "original_error_code": null,
  "ui_error_code": null,
  "expectation_met": true
}
```

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
- timing capture;
- request-error capture;
- refusal of remote plain HTTP credentials;
- aggregate gate evaluation;
- refusal to close the failure-pair gate without observed UI codes.

These tests validate the measurement tooling. They do **not** substitute for the live exit gate.

## Phase 0 exit gate

Current status:

- [ ] `hello`, one read, one action and one failure have live reproducible captures in a real
  embedded Odoo + authenticated Codex environment.
- [ ] A live turn has been decomposed into queue/provider/tool/finalization timing using the
  implemented checkpoints.
- [ ] The simple-turn latency has been attributed from measured live data rather than guessed.
- [ ] At least five important failure paths have original code + final UI code recorded side by
  side.

The repository now has the scenario contract, client/provider instrumentation, redacted live
capture runner, summarizer and aggregate gate evaluator needed for those measurements. The gate
remains open because this environment does not provide the real authenticated Odoo/Codex instance
or browser observations required to produce the evidence.

## Next work inside Phase 0

Stay in Phase 0. Do **not** begin the provider-boundary refactor yet.

Next:

1. run the minimum live matrix with `phase0_live_capture.py`;
2. inspect the first aggregate report for inconsistent or missing timestamps;
3. capture five original-vs-UI error pairs with controlled fixtures;
4. repeat `hello` and a simple read enough to establish a useful baseline distribution;
5. add capture adapters for `plan_decision`, cancellation or recovery only if those scenarios are
   needed to close an evidence gap;
6. only then let `phase0_report.py` decide whether Phase 1 may start.
