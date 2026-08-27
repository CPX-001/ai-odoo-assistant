# Phase 2 — structured failure contract

Date: 2026-08-28
Inspected implementation/test base: `33ca2bfaeebb85f0675594b27c6d52cbd7bc8dcf`
Status: `IN_PROGRESS`

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
