# Agent runtime optimization

Current performance/quality guidance for the embedded Odoo runtime. Sidecar-era timeout, proxy and separate-service tuning in older milestone material is historical.

## Optimization objective

Optimize useful product latency and agent quality without weakening host authority. The relevant path is now:

```text
submit/persist -> queue claim -> context/catalog build -> Codex reasoning
 -> capability execution/retrieval -> verification -> persisted result/events -> UI render
```

A faster response that chooses the wrong capability, leaks evidence, skips verification or increases write ambiguity is a regression.

## Measure before changing architecture

Instrument or derive per-turn timings for at least:

- submit/persistence latency;
- queue wait and lease/claim time;
- effective context/catalog construction;
- provider startup/handshake;
- model generation/tool-selection time;
- each capability call;
- approval wait (separate from compute latency);
- effect execution and verification;
- final result/event persistence;
- browser-visible time to useful progress and final answer.

Correlate by turn/capability/source identifiers while keeping prompt/arguments/results content redacted by default.

## Main optimization levers

### Context and capability surface

Keep the effective tool/context surface compact. Improve descriptions and selection metadata before simply adding more tools. If catalog scale later causes measurable regressions, evaluate progressive disclosure/lazy bundles rather than sending everything on every turn.

### Provider lifecycle

Codex is an ephemeral provider subprocess. Optimize startup/handshake only with measurements; do not turn it into an unbounded long-lived product daemon unless a new ADR demonstrates a concrete need.

### Queue

The Odoo-native queue is part of the architecture, not incidental overhead. Tune cron concurrency/lease behavior against real deployment conditions while preserving restart/cancellation/recovery semantics.

### Capability calls

Prefer bounded server-side operations over model-authored loops. Use batch operations where the current capability contract can preserve previews, budgets and verification.

### Retrieval

When retrieval exists, route by evidence type and fetch just-in-time. Avoid context dumps. Cache/index only where freshness, provenance and invalidation are explicit.

### UI progress

Perceived latency improves when the UI exposes honest, sanitized host states. Persist meaningful progress categories; do not stream private reasoning as a latency workaround.

## Quality/eval guard

Performance work involving model context, capability descriptions, tool exposure, retries or provider settings must be evaluated on task outcomes, not latency alone. Track at minimum:

- correct capability/tool choice;
- schema-valid calls;
- grounding/evidence quality;
- ACL/policy behavior;
- unauthorized-write rate (must remain zero);
- completion/recovery correctness;
- token/cost/latency budget.

## Anti-patterns

Do not optimize the current product by:

- restoring a FastAPI sidecar just to reuse old timings;
- bypassing durable turn persistence;
- using `sudo()`/technical credentials to avoid permission costs;
- increasing record/context limits without evidence;
- retrying ambiguous writes automatically;
- suppressing verification to reduce response time;
- logging raw prompts/tool payloads for easier profiling.

## Benchmark discipline

Keep representative query, action, approval, ACL-denial, provider-error and recovery scenarios. Compare performance by code/provider/model baseline and retain enough metadata to explain regressions. Deterministic tests protect contracts; agentic evals protect model behavior.