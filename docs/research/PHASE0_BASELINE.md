# Phase 0 reproducible baseline

Research/playbook source: `FOUNDATION_STABILIZATION_PLAYBOOK.md`  
Phase started from main: `3f175cdc9b38aa3fc5aac4f231c0aee5d86b46ef`  
Target: Odoo 18 Community / embedded runtime / Codex primary  
Status: **in progress — measurement scaffolding implemented, live exit gate not yet satisfied**

## Purpose

Phase 0 exists to stop debugging latency and failures by impression. It must produce repeatable scenarios and enough timing/error evidence to attribute a slow or failed turn before any provider-lifecycle, streaming, UI, or latency architecture is changed.

This document is an execution record, not current-state architecture authority. Current code, accepted ADRs and the documents indexed by `docs/README.md` remain authoritative.

## Implemented in this slice

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

`streamAssistantChat()` now has optional `onTiming` and `nowCall` diagnostic hooks. The normal product caller can ignore them.

Current client checkpoints:

```text
submit_received
turn_persisted
browser_first_activity
browser_final
```

`nowCall` defaults to `performance.now()` with a `Date.now()` fallback. Tests inject a deterministic clock. The callback receives only checkpoint name, elapsed milliseconds and minimal turn/state metadata.

Important: the current `onDelta` path is still progress labels derived from polling. Therefore this phase does **not** record `browser_first_answer_delta`, because doing so would falsely label progress text as assistant answer streaming.

### 3. Baseline trace summarizer

`tests/e2e/phase0_baseline.py` consumes a captured trace and merges:

- client monotonic checkpoints;
- persisted Odoo turn-event timestamps;
- future `diagnostic.timing` backend events when they become available;
- final state/error codes;
- optional model-turn/tool-call/token counters.

Current persisted-event mappings are intentionally explicit:

| Phase 0 point | Current evidence |
| --- | --- |
| `turn_persisted` | `queued` event, overridden by client monotonic submit timing when available |
| `worker_claimed` | `started` event |
| `runtime_started` | `reasoning.started` event as a documented proxy |
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
runtime_started                 proxy via reasoning.started
provider_process_started        MISSING dedicated backend checkpoint
provider_initialized            MISSING dedicated backend checkpoint
provider_thread_started         MISSING dedicated backend checkpoint
provider_turn_started           MISSING dedicated backend checkpoint
first_provider_event            MISSING dedicated backend checkpoint
first_answer_delta              MISSING; adapter currently ignores answer deltas for product transport
first_capability_started        covered by tool.started
last_capability_completed       covered by tool.completed/tool.failed
reasoning_completed             covered by reasoning.completed
result_persisted                covered by terminal/approval event
browser_first_activity          covered client-side
browser_first_answer_delta      MISSING by design until real answer streaming exists
browser_final                   covered client-side
```

The missing provider checkpoints are the next Phase 0 coding slice. They should be added at the Codex adapter boundary using process-local monotonic time and a sanitized diagnostic projection. They must not expose raw provider notifications or model content.

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
- [ ] A turn can be decomposed into queue/provider/tool/finalization timing with the dedicated provider checkpoints above.
- [ ] The simple-turn latency can be attributed from measured data rather than guessed.
- [ ] At least five important failure paths have original code + final UI code recorded side by side.

The repository now has the scenario contract, client measurement hooks and trace summarizer needed for those captures, but the gate remains open until provider-side timing instrumentation and live measurements are added.

## Next coding slice

Stay in Phase 0. Do **not** begin the provider-boundary refactor yet.

Next:

1. add sanitized monotonic checkpoints around Codex process start/initialize, thread start, turn start and first provider event;
2. observe `item/agentMessage/delta` only enough to measure `first_answer_delta` without changing the product streaming transport;
3. expose those checkpoints to the trace collector without raw protocol content;
4. execute the minimum live matrix (`hello`, read, action, failure) and record the first baseline;
5. only then evaluate the Phase 0 exit gate.
