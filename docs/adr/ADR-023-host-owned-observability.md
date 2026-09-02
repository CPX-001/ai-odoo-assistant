# ADR-023 — Host-owned, content-minimal observability

Status: Accepted architecture; implementation proceeds incrementally in P8  
Date: 2026-09-02

## Context

The product must explain why a turn failed or was slow across queueing, provider
decisions, capability calls, retrieval, approval, effects, verification and UI
delivery. Existing Odoo turns/events/effect receipts already provide a durable base,
but there is no complete cross-layer taxonomy. Logging prompts, tool payloads or
private reasoning would create a second secret/PII store and an unsafe UX.

## Decision

Use Odoo-owned turns, activities, events and receipts as the primary trace. Add a
host-owned hierarchy and stable correlation IDs:

```text
assistant.turn
  provider.decision / provider.generation
  capability.call
  evidence.search / evidence.fetch
  effect.preview
  approval.wait
  effect.execute
  effect.verify
  ui.delivery
```

Default telemetry contains operation metadata, timing, outcome/error code, bounded
counts/bytes, queue wait, model/profile, usage/cost when available and freshness/
cache state. Full prompts, private reasoning, complete args/results, retrieved
content, PII and secrets are excluded by default.

Detailed diagnostic content is opt-in, authorized, redacted, bounded and retained
with a finite TTL. Public activity is a sanitized product projection rather than a
raw trace.

Conceptually compatible OpenTelemetry names may be used, but the product does not
require an external collector, tracing sidecar, database or scheduler.

## Secret handling

A secret pasted by a user does not automatically block the turn. Derived Evidence,
trace and progress projections must omit/redact it where possible, the user receives
a warning, and safe work may continue. Assistant-presented secrets use a dedicated
masked/copy/reveal UI and never public progress.

## Self-inspection

Future safe READ capabilities expose sanitized projections:

```text
assistant.runtime_health
assistant.inspect_turn
assistant.get_recent_failure
assistant.explain_latency
assistant.configuration_health
```

Users see only owned/authorized data. Global/cross-user diagnostics require the
Technical profile and applicable Odoo permissions. These capabilities do not expose
raw traces or grant host privilege.

## Failure behavior

Read-only/pre-effect failures may start a bounded diagnosis continuation using
correlated runtime/log/source Evidence. Ambiguous effects are not automatically
retried: they become `recovery_required`/`uncertain` with receipts and recovery
instructions. Provider-total failure returns only deterministic host-known state;
it does not invent a cause.

## Consequences

Positive:

- latency and failure analysis shares the existing durable Odoo lifecycle;
- public progress can remain useful without exposing chain-of-thought;
- Evidence and effect operations gain consistent correlation;
- deployments may export compatible telemetry later without changing authority.

Costs:

- every layer must emit sanitized metadata consistently;
- content diagnostics need explicit retention and access policy;
- evals must verify absence of secret/private payload leakage.

## Rejected alternatives

- Logging full prompts/tools/results by default.
- Treating provider private reasoning as a debug trace.
- Introducing a mandatory external tracing service or sidecar.
- Reconstructing authority from correlation IDs.
- Automatically retrying ambiguous writes because a trace reports an error.

## Implementation note

The P8 foundation establishes Evidence IDs/request metadata and this contract. The
full span/event projection, self-inspection capabilities and diagnostic UI remain
subsequent P8 slices and cannot be reported complete before their focused/real gates.
