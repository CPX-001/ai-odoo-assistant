# Phase 0 reproducible baseline

Research/playbook source: `FOUNDATION_STABILIZATION_PLAYBOOK.md`  
Phase started from main: `3f175cdc9b38aa3fc5aac4f231c0aee5d86b46ef`  
Target: Odoo 18 Community / embedded runtime / Codex primary  
Status: **in progress — client/provider measurement instrumentation implemented, live exit gate not yet satisfied**

## Purpose

Phase 0 exists to stop debugging latency and failures by impression. It must produce repeatable scenarios and enough timing/error evidence to attribute a slow or failed turn before any provider-lifecycle, streaming, UI, or latency architecture is changed.

This document is an execution record, not current-state architecture authority. Current code, accepted ADRs and the documents indexed by `docs/README.md` remain authoritative.

## Implemented in this phase

### 1. Machine-readable scenario matrix

`tests/e2e/embedded_phase0_scenarios.json` now defines the permanent baseline scenarios required by the stabilization playbook:

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

A deterministic unit test validates that the catalog remains complete, bounded and structurally valid.

The catalog deliberately records fixture requirements instead of hiding setup assumptions inside prose. It does not contain credentials, business payloads or prompt text.

### 2. Browser monotonic timing checkpoints

`streamAssistantChat()` has optional `onTiming` and `nowCall` diagnostic hooks. The normal product caller can ignore them.

Current client checkpoints:

```text
submit_received
turn_persisted
browser_first_activity
browser_final
```

`nowCall` defaults to `performance.now()` with a `Date.now()` fallback. Tests inject a deterministic clock. The callback receives only checkpoint name, elapsed milliseconds and minimal turn/state metadata.

Important: the current `onDelta` path is still progress labels derived from polling. Therefore Phase 0 does **not** record `browser_first_answer_delta`, because doing so would falsely label progress text as assistant answer streaming.

### 3. Codex provider monotonic checkpoints

`CodexReasoningEngine` now creates one best-effort, content-free monotonic recorder per provider run. It emits sanitized `diagnostic.timing` events through the existing `CapabilityContext` event sink.

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

`first_answer_delta` is timing-only. The adapter notices the already-allowed `item/agentMessage/delta` notification method but does not persist or forward its text. This deliberately does **not** implement product answer streaming ahead of Phase 4.

The diagnostic event payload is limited to:

```json
{"point": "provider_initialized", "elapsed_ms": 123.456}
```

The recorder is idempotent per point and best-effort: a failure to persist diagnostic timing must not fail a product turn. No raw provider notification, prompt, output, tool arguments, stdout/stderr or credential data is added.

### 4. Baseline trace summarizer

`tests/e2e/phase0_baseline.py` consumes a captured trace and combines:

- client monotonic checkpoints;
- persisted Odoo turn-event timestamps;
- provider `diagnostic.timing` events;
- final state/error codes;
- optional model-turn/tool-call/token counters.

Clock domains are kept explicit. `timings_ms` is a submit-relative product timeline: server timestamps are measured from the persisted `queued` event and shifted by the observed client `turn_persisted` latency when available. `runtime_monotonic_ms` preserves provider process-local monotonic offsets separately; the summarizer does not pretend browser and cron workers share one monotonic clock.

Current evidence mappings are intentionally explicit:

| Phase 0 point | Current evidence |
| --- | --- |
| `turn_persisted` | client monotonic timing + `queued` event |
| `worker_claimed` | `started` event |
| `runtime_started` | `reasoning.started` wall-clock proxy + `diagnostic.timing` monotonic checkpoint |
| provider lifecycle points | `diagnostic.timing` event timestamp + runtime monotonic offset |
| `first_answer_delta` | timing-only `diagnostic.timing`; answer text is not persisted |
| `first_capability_started` | first `tool.started` event |
| `last_capability_completed` | last `tool.completed` / `tool.failed` event |
| `reasoning_completed` | `reasoning.completed` event |
| `result_persisted` | first terminal/approval event visible after authoritative state persistence |
| `submit_received` / browser points | client `onTiming` |

The summarizer reports every required but missing checkpoint instead of fabricating values.

## Trace contract

A capture runner should write one JSON object per trial with this shape:

```json
{
  "scenario_id": "hello",
  "timings": [
    {"point": "submit_received", "elapsed_ms": 0},
    {"point": "turn_persisted", "elapsed_ms": 24.3},
    {"point": "browser_first_activity", "elapsed_ms": 25.1},
    {"point": "browser_final", "elapsed_ms": 10342.8}
  ],
  "status_snapshots": [
    {"state": "queued", "events": []},
    {"state": "completed", "error_code": null, "events": []}
  ],
  "original_error_code": null,
  "ui_error_code": null,
  "model_turns": 1,
  "tool_calls": 0,
  "token_usage": null
}
```

Do not put message text, prompts, raw tool arguments/results, auth data, stdout/stderr or provider secrets in baseline traces.

Run the summarizer with:

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

The only intentionally missing answer-stream checkpoint is browser-side first answer delta. That belongs to the later real-streaming phase; Phase 0 can still measure whether Codex produced a delta and how long it took.

## Error-pair capture

For failure scenarios the baseline must retain two values side by side:

```text
original_error_code
ui_error_code
```

The first is the most specific sanitized code observed before presentation flattening. The second is what the browser/product finally sees. This is measurement only; changing the failure taxonomy belongs to the later failure-contract phase.

At least these five failure families must be captured before Phase 0 closes:

1. provider auth missing;
2. provider process missing;
3. provider disconnect/EOF;
4. provider timeout;
5. invalid capability/provider output.

Additional recommended pairs: ACL denied, cancellation and write-recovery-required.

## Trial protocol

For each scenario:

1. reset/verify the named fixture requirements;
2. capture client timings and every Odoo status envelope returned to that user;
3. record final state and normalized error code;
4. add original provider/capability code when the injection fixture exposes it safely;
5. record model turns, tool calls and token usage when available;
6. run `phase0_baseline.py`;
7. retain the summary, not raw prompts/tool payloads.

For latency distributions, run `hello` and one simple read repeatedly. Do not use a single warm run as evidence. The Phase 1 gate later requires at least 100 repeated simple turns without protocol-shape failures.

## Phase 0 exit gate

Current status:

- [ ] `hello`, one read, one action and one failure have live reproducible captures in a real embedded Odoo + authenticated Codex environment.
- [ ] A live turn has been decomposed into queue/provider/tool/finalization timing using the implemented checkpoints.
- [ ] The simple-turn latency has been attributed from measured live data rather than guessed.
- [ ] At least five important failure paths have original code + final UI code recorded side by side.

The repository now has the scenario contract, client/provider measurement hooks and trace summarizer needed for those captures. The gate remains open because the required live authenticated measurements and failure-pair evidence have not been produced in this environment.

## Next work inside Phase 0

Stay in Phase 0. Do **not** begin the provider-boundary refactor yet.

Next:

1. execute the minimum live matrix (`hello`, one read, one action, one failure) on a real embedded Odoo 18 instance with an authenticated Codex account;
2. inspect the first summaries and confirm queue/provider/tool/finalization attribution is internally consistent;
3. capture at least five original-vs-UI error pairs using controlled failure fixtures;
4. repeat simple turns enough to establish a useful baseline distribution;
5. only then evaluate the Phase 0 exit gate and decide whether Phase 1 may start.
