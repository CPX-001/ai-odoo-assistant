# Host-owned observability architecture

Status: architectural contract accepted for implementation sequencing; the P8.0/P8.2
checkpoint adds the Evidence correlation seam, not a complete tracing subsystem.

## Objective

Make turns diagnosable without persisting private reasoning, credentials, full
prompts or unbounded business/source payloads. Odoo remains the persistence and
access-control authority. Observability enriches existing turns, activities,
events and effect receipts; it does not introduce a second operational database or
required sidecar.

## Span hierarchy

```text
assistant.turn
  provider.decision / provider.generation
  capability.call
  evidence.search / evidence.fetch
  effect.preview
  approval.wait          # only when policy requires it
  effect.execute
  effect.verify
  ui.delivery
```

Stable correlation fields:

```text
conversation_id
turn_id
provider_decision_id
capability_call_id
evidence_request_id / evidence_id
effect_plan_id / effect_step_id
activity_id
```

A child operation must retain the effective user/company binding of its parent.
Correlation IDs are identifiers, not authorization tokens.

## Default telemetry

Capture by default:

- component and operation;
- start/end/duration and queue wait;
- outcome and sanitized error code;
- counts and bounded byte totals;
- provider model/profile and available usage/cost counters;
- cache/freshness status;
- retry/recovery classification.

Do not capture by default:

- full prompts or model responses;
- private provider reasoning;
- complete capability arguments/results;
- retrieved excerpts or documents;
- credentials, secrets or authorization headers;
- unbounded PII, logs or source payloads.

Authorized diagnostic mode may retain additional redacted, bounded content with an
explicit TTL and access scope. It still cannot persist provider private reasoning.

## Public versus host-only projection

Public progress is a sanitized product projection:

```text
queued -> analyzing -> retrieving -> consulting_odoo
-> preparing_change -> awaiting_approval (when required)
-> executing -> verifying -> composing -> completed/failed/recovery_required
```

The UI may show duration, step count and current activity. It must not reconstruct
or display chain-of-thought, raw tool arguments, stdout or secrets.

Host-only diagnostics may correlate sanitized errors with Evidence providers for
runtime, logs and source. A user can inspect only owned turns/data. Cross-user or
global diagnostics require the Technical profile plus applicable Odoo permissions.

## Self-inspection capabilities

Planned safe READ capabilities:

```text
assistant.runtime_health
assistant.inspect_turn
assistant.get_recent_failure
assistant.explain_latency
assistant.configuration_health
```

They consume sanitized Odoo-owned projections, never raw traces. They do not grant
additional capabilities or host privilege.

## Failure diagnosis

Read-only or pre-effect failure:

```text
failure envelope
 -> correlate turn/operation
 -> route bounded Evidence to runtime/log/source providers
 -> produce a diagnosis continuation
 -> answer with observed facts, probable cause and next safe action
```

Ambiguous effect failure:

```text
no automatic retry
 -> recovery_required / uncertain
 -> expose effect receipt and verification state
 -> give a bounded recovery procedure
```

When the provider itself is unavailable, a deterministic host fallback may report
the sanitized error code, effect state and operational next steps. It must not
invent a root cause.

## Secret handling

User-provided secrets do not automatically block a turn. The product should:

1. accept the message;
2. prevent the value from becoming instruction or authority;
3. redact derived traces, Evidence and public progress where possible;
4. warn about the exposure without unnecessarily repeating the value;
5. continue when the requested operation remains safe.

Assistant-presented secrets require a dedicated UI value: masked by default, copy
action and optional reveal/hide. Secret values never enter public progress or
Diagnostics summaries.

## Implementation constraints

- Reuse durable turn/event/effect models.
- Use Odoo access rules and retention controls.
- Adopt OpenTelemetry-compatible names only where they clarify semantics; no
  external collector is required for the product to work.
- No raw prompt/result logging as a shortcut.
- No tracing sidecar or separate scheduler.
- No claim of completed observability until deterministic, Odoo and real gates are
  executed and recorded.
