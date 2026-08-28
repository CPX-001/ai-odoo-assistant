# Phase 2 — structured failure contract

Date: 2026-08-28
Inspected implementation/test base: `33ca2bfaeebb85f0675594b27c6d52cbd7bc8dcf`
Status: `COMPLETE`

## Goal

Preserve machine-usable facts from the component that actually failed through the Odoo-owned turn path without exposing secrets, provider stderr, raw prompts or unrestricted payloads.

Phase 2 follows the completed provider-boundary stabilization. It must establish failure semantics before browser copy, public activity, answer streaming or retry UX is redesigned.

## Current observed failure projection

Inspection of the Phase 2 entry checkpoint found four distinct flattening layers:

- `odoo.ai.turn` persists only `error_code`; `browser_status()` returns that code but no structured category, stage, effect state or remediation facts.
- controller `_error()` responses contain only `{"ok": false, "error": {"code": ...}}`.
- the non-stream browser path propagates only a known string code by throwing `Error(code)`.
- `submitStreamingAssistantRequest()` catches every thrown error and replaces it with `service_unavailable`, so provider/auth/timeout/tool/access specificity is lost before presentation.

`assistant_failure_messages.js` then maps a small set of codes directly to prose. That file is presentation policy, not a sufficient machine contract.

The first Phase 2 slice therefore defines the contract only. It does not yet alter persistence, controller payloads or browser behavior.

---

# P2.1 — FailureEnvelope schema

```text
phase: 2
state: COMPLETE
inspected_head: 33ca2bfaeebb85f0675594b27c6d52cbd7bc8dcf
gate_type: HARD
lookahead_eligible: no
```

## Objective

Create one provider-neutral, bounded `FailureEnvelope` value contract that later slices can use to normalize provider, queue, capability, Odoo and browser failures without scattering routing semantics across strings and UI code.

## Why this slice exists

Phase 1 intentionally preserved only bounded provider facts and advisory retryability. The current turn/browser path still has no host-owned structure able to express category, stage, effect certainty or required user action. P2.1 creates that structure before any mapping or presentation layer consumes it.

## Prerequisites

- Phase 0 complete.
- Phase 1 complete, including `P1-REAL-VERSION`, `P1-REAL-SOAK-100`, `P1-REAL-TOOLCALL` and `P1-REAL-CANCEL`.
- Odoo remains host/persistence authority.
- `CapabilityDefinition` remains the atomic executable contract.
- Phase 1 provider retryability remains advisory only.

Unresolved prerequisite validation debt: none.

## Dependency on unvalidated contracts

```text
depends_on_unvalidated_contracts:
  - none
creates_new_production_contract: yes
stacked_unvalidated_contract_layers_after_slice: 0
```

The new contract is dependency-light and deterministically validated in this slice. It is not yet wired into runtime behavior, so it creates no real-environment validation debt by itself.

## Gate classification

`HARD`: P2.2 and later failure-normalization/browser slices will consume this exact schema. A malformed or ambiguous envelope would force downstream redesign, especially around retryability and write-effect uncertainty.

## Likely affected areas

Implemented:

```text
addons/odoo_ai_assistant/runtime/agent/failure.py
tests/unit/test_failure_envelope_contract.py
docs/research/PHASE2_FAILURE_CONTRACT.md
docs/research/EXECUTION_STATE.md
```

Inspected but deliberately unchanged in P2.1:

```text
addons/odoo_ai_assistant/models/turn_queue.py
addons/odoo_ai_assistant/controllers/turn_runtime.py
addons/odoo_ai_assistant/static/src/services/assistant_panel_service.js
addons/odoo_ai_assistant/static/src/services/assistant_panel_streaming_service.js
addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_failure_messages.js
```

## Invariants

- No business capability, policy, approval, write barrier, verification or ACL behavior changes.
- No automatic retry is introduced.
- `effect_state` is an explicit fact in the contract; later code may not infer “no effect” merely from a provider failure.
- Raw provider messages/details, credentials, prompts, stderr/stdout and unrestricted tool payloads are not fields of the envelope.
- `safe_details` is bounded JSON data only; the producing host code remains responsible for semantic redaction.
- Unknown/extra top-level fields fail closed.
- Odoo effective-user execution and `su=False` remain unchanged.

## Failure modes considered

- unbounded detail payloads becoming a secret/log exfiltration channel;
- UI/product behavior depending on hundreds of ad-hoc categories;
- ambiguous retry flags that encourage unsafe write replay;
- effect uncertainty being omitted from terminal failures;
- arbitrary provider text being mistaken for a browser-safe summary;
- downstream consumers accepting unknown schema fields silently.

## Implementation scope

`failure.py` now defines:

- `FailureEnvelope`;
- strict parser and fixed payload serializer;
- a closed JSON Schema projection;
- the Phase 2 category taxonomy from the stabilization playbook;
- bounded stage/component taxonomies;
- `retryability = never | safe | after_change | unknown`;
- `effect_state = none | not_started | confirmed | partial | unknown`;
- `user_action = retry | reconnect | clarify | request_access | review | none`;
- bounded identifiers, one-line safe summary and a 4 KiB structured `safe_details` budget.

## Explicitly out of scope

- mapping `CodexDecisionError` or Phase 1 provider facts into the envelope;
- persisting the envelope on `odoo.ai.turn`;
- returning the envelope through `/turn/status`;
- changing frontend normalization or error copy;
- retry buttons or automatic retry;
- public activity/answer streaming;
- AI-generated failure prose.

## Deterministic validation

Executed in the ChatGPT isolated Python workspace using the exact proposed target paths/files for this dependency-light slice:

```text
python -m py_compile \
  addons/odoo_ai_assistant/runtime/agent/failure.py \
  tests/unit/test_failure_envelope_contract.py
PASS

python -m pytest -q tests/unit/test_failure_envelope_contract.py
5 passed, 17 subtests passed
```

The focused contract suite verifies fixed-shape round-trip, bounded routing taxonomies, fail-closed unknown/invalid values, JSON/detail bounds and the closed schema projection.

A full repository/Odoo suite was not executed in this environment. That is not a completion blocker for P2.1 because the new module is not imported by the runtime yet; the first consuming slice must run its own deterministic integration coverage before it can complete.

## Real-environment validation

```text
required_validation_ids:
  - none directly for P2.1
```

Phase-level completion still requires:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

Those become materially applicable only after later slices propagate the envelope through the real turn/browser path.

## Validation debt created

None for P2.1.

## Exit criteria

- [x] One closed bounded `FailureEnvelope` contract exists.
- [x] Product category/retry/effect/action enums are explicit.
- [x] Unsafe/unbounded detail shapes fail closed.
- [x] Focused dependency-light tests and Python compilation pass.
- [x] No runtime/browser behavior is changed in this slice.
- [x] Phase 2 execution state is durable in Git.

## Result / discoveries

The current product already preserves enough individual error codes to seed Phase 2, but it loses their semantics at different boundaries. The worst browser loss is the streaming submit catch-all to `service_unavailable`. This confirms the playbook ordering: normalize backend/provider facts first, then persist/project them, then repair browser behavior and presentation.

No ADR is required for P2.1 because the contract does not alter deployment, authority, provider lifecycle, write semantics or persistence architecture.

## Next action

Implement only `P2.2-codex-error-normalization`: map existing sanitized provider/host terminal facts into `FailureEnvelope` at the host failure boundary with deterministic tests. Preserve the existing write barrier and do not yet change browser copy, add retries or implement Phase 3 public activity.

---

# P2.2 — Codex/provider error normalization

```text
phase: 2
state: COMPLETE
inspected_head: 70d424cb52c456009fbc704bd8d00112436636b0
gate_type: HARD
lookahead_eligible: no
```

## Objective

Normalize failures raised by the active decision provider into the P2.1 `FailureEnvelope` before
`AgentTurnService` or the queue flatten them to a code, while preserving the existing product error
code and all host authority/recovery semantics.

## Why this slice exists

Phase 1 retained safe `CodexDecisionError` facts (`category`, bounded HTTP status, bounded upstream
code and advisory `provider_retryable`) but the active host loop did not consume them. Plain Codex
transport/protocol errors also crossed the boundary only as a string code.

P2.2 introduces a provider-boundary decorator. It does not persist or expose the envelope yet.

## Dependency on unvalidated contracts

```text
depends_on_unvalidated_contracts:
  - none
creates_new_production_contract: yes
stacked_unvalidated_contract_layers_after_slice: 0
```

The slice consumes the deterministically validated P2.1 schema. The outward turn/browser contract is
unchanged, so Phase 2 real presentation gates are not materially testable yet.

## Implementation

Added `runtime/agent/provider_failure.py`:

```text
CodexDecisionEngine
  -> FailureNormalizingDecisionEngine
      -> provider exception
      -> normalize_provider_failure(...)
      -> ProviderFailureError(AgentTurnError)
          .code     preserved
          .failure  validated FailureEnvelope
```

`failure.py` now contains the bounded provider projection. It uses only already-sanitized attributes
from the exception and never reads provider message text, stderr, prompts, request bodies or
`additionalDetails`.

Current routing includes distinct product behavior for authentication, provider capacity,
connection/stream failures, context limits, protocol failures, provider output failures,
cancellation and unknown/internal provider failures. Unknown future provider codes fall back to
`internal + retryability=unknown` instead of inventing specificity.

### Effect-state derivation

The active host loop wraps only `CodexDecisionEngine.next_decision()` and sets:

```text
effect_state = none
```

This is not inferred from provider metadata. At this exact boundary the provider can only return a
decision; the host may execute REASONING capabilities or stage one PLAN proposal, while the durable
write barrier and effectful plan execution occur later and outside the wrapper. Authorized-plan
resume bypasses the provider boundary entirely.

`serverOverloaded` becomes `retryability=safe` only when both conditions hold:

```text
provider_retryable == true
effect_state in {none, not_started}
```

The slice still does not perform an automatic retry.

## Files changed

```text
addons/odoo_ai_assistant/runtime/agent/failure.py
addons/odoo_ai_assistant/runtime/agent/provider_failure.py
addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py
tests/unit/test_provider_failure_normalization.py
docs/research/PHASE2_FAILURE_CONTRACT.md
docs/research/EXECUTION_STATE.md
```

## Deterministic validation actually executed

An isolated dependency-light workspace contained the exact proposed target files and
repository-relative paths:

```text
python -m py_compile \
  addons/odoo_ai_assistant/runtime/agent/failure.py \
  addons/odoo_ai_assistant/runtime/agent/provider_failure.py \
  addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py \
  tests/unit/test_failure_envelope_contract.py \
  tests/unit/test_provider_failure_normalization.py
PASS

python -m pytest -q \
  tests/unit/test_failure_envelope_contract.py \
  tests/unit/test_provider_failure_normalization.py
12 passed, 17 subtests passed
```

A lightweight runtime-stub execution also proved the wrapper converts an effect-safe
`serverOverloaded` provider error into:

```text
code=codex_turn_failed
category=provider_capacity
retryability=safe
effect_state=none
```

No GitHub Actions or real Odoo/Codex environment were used. Full repository/Odoo batteries are not
being reported as PASS.

## Real-environment validation

```text
required_validation_ids:
  - none directly for P2.2
```

The Phase 2 completion gates remain:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

They require a later slice to persist/project the envelope through the turn/browser boundary.

## Invariants retained

- Odoo remains operational/persistence authority.
- Effective-user capability execution and `su=False` are unchanged.
- The provider cannot execute business effects.
- Preview/approval/write barrier/verification semantics are unchanged.
- The original product `code` remains the queue/retry discriminator for now.
- `provider_retryable` remains advisory; only explicit effect state can make overload retry-safe.
- No automatic provider, capability or write retry is added.
- No raw provider text or secret-bearing payload is copied into `FailureEnvelope`.

## Exit criteria

- [x] Current sanitized Codex terminal facts map to `FailureEnvelope`.
- [x] Plain provider transport/protocol/output codes receive bounded product categories.
- [x] The active host-loop provider boundary carries the envelope without changing outward turn status.
- [x] Effect state is explicit and is not inferred from a generic provider failure.
- [x] Safe overload classification requires both provider retryability and safe effect state.
- [x] Focused dependency-light tests and compilation pass.
- [x] No persistence/browser/error-copy/retry behavior is added.

## Result / discoveries

The cleanest boundary was not inside the Codex adapter and not inside `AgentTurnService`. A thin
provider-neutral decorator keeps Phase 1 provider code isolated while letting the host own product
failure semantics. It also means a future provider can use the same failure contract without
duplicating queue or browser logic.

## Next action

Implement `P2.3-turn-failure-persistence`: persist the validated envelope on terminal turn failure
and project it through `browser_status()` without yet rewriting browser copy or adding retry
buttons. The queue write barrier must remain the authority for `effect_state` when the failure
occurs after effect execution has become possible.

---

# P2.3 — terminal turn persistence closeout

```text
phase: 2
state: COMPLETE
materially_validated_checkpoint: 8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
gate_type: HARD
```

The validated `FailureEnvelope` is now stored on terminal `odoo.ai.turn` records and projected as
`browser_status().failure`, while the compatibility `error_code` remains unchanged. The queue write
barrier still owns effect certainty and forces uncertain effectful failures into the no-blind-retry
recovery path.

Real Odoo 18 validation on a disposable database passed addon install/update, the focused failure
persistence and queue suites, and the full addon battery. The initial focused run found and repaired
an overwrite bug in which a later event-sequence write replaced the carried provider envelope with a
generic fallback. After repair, unrelated writes preserve the original validated envelope.

```text
P2.3-ODOO-UPDATE  PASS
P2.3-ODOO-FAILURE PASS
full addon battery 95 passed, 0 failed, 0 errors
HOOT addon battery 78 passed, 0 failed
```

Evidence: `docs/research/evidence/phase2/2026-08-28/P2.3-ODOO-VALIDATION-8683ef6.md`.

Phase 2 remains `IN_PROGRESS`. Its browser consumer/presentation slice is not implemented, so the
five `P2-REAL-*` presentation validations are not yet materially executable and remain mandatory.

## Next action

Implement `P2.4-browser-failure-presentation` as the smallest coherent consumer of the persisted
browser-safe failure projection. Then run `P2-REAL-AUTH`, `P2-REAL-ACL`, `P2-REAL-TIMEOUT`,
`P2-REAL-TOOLFAIL` and `P2-REAL-RECOVERY` before selecting Phase 3.

## Phase 2 completion note

P2.4 and all five `P2-REAL-*` gates subsequently passed on
`ba4ba00f9a913854a21b571cbb4559105347cca2`. See
`evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`. The earlier per-slice next-action sections are
retained as execution history rather than current instructions.
