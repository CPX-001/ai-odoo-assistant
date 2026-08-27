# Stabilization execution state

State format: 3
Updated: 2026-08-28
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 2
phase_name: structured failure contract
phase_state: IN_PROGRESS
active_phase_record: docs/research/PHASE2_FAILURE_CONTRACT.md
active_slice: P2.3-turn-failure-persistence
active_slice_record: docs/research/P2.3_TURN_FAILURE_PERSISTENCE.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: HARD_LOCAL_ODOO
blocking_validations: P2.3-ODOO-UPDATE, P2.3-ODOO-FAILURE
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: NONE_UNTIL_P2.3_ODOO_VALIDATION
```

Phase 0 and Phase 1 are complete. Phase 2 has implemented its schema, provider normalization and
terminal turn persistence slices. P2.3 is **not complete yet** because the new stored Odoo field and
model override have not been exercised by an Odoo 18 module update/test run.

## P2.3 implementation checkpoint

P2.3 reconstructed remote `main` at:

```text
d12f73e50a896315a6f4b0051d6e0125de621554
```

The material implementation reached:

```text
00d963e0bdf1a14efe55fb974c2642de038313ee
```

The following docs-only handoff then recorded the validation gate:

```text
e90264ab3c1d72afbdbe92b79fdc5a2b6012c718
```

## Phase 2 progress

### P2.1 — FailureEnvelope schema

`COMPLETE`.

The bounded host contract remains:

```text
code
category
stage
component
retryability
effect_state
user_action
safe_summary
safe_details
diagnostic_id
provider_code
```

### P2.2 — Codex/provider normalization

`COMPLETE`.

The active provider boundary preserves sanitized provider category, bounded HTTP status, bounded
upstream code and advisory retryability inside a validated `FailureEnvelope`. Raw provider text,
credentials, stdout/stderr, prompts and unrestricted payloads are not copied.

### P2.3 — terminal turn persistence

`LOCAL_VALIDATION_REQUIRED`.

Implemented behavior:

```text
ProviderFailureError.failure
        |
        v
terminal_failure_envelope(...)
        |
        +-- write_barrier=false -> effect_state=none
        |
        +-- write_barrier=true  -> effect_state=unknown
                                 retryability=never
                                 user_action=review
        |
        v
odoo.ai.turn.failure_payload
        |
        v
browser_status().failure

browser_status().error_code remains for compatibility
```

`models/turn_failure.py` preserves the original queue retry/failure state machine for ordinary
errors. A specialized finalizer is used only when the exception already carries a validated provider
envelope so P2.2 facts survive atomically. Generic terminal writes receive a bounded host fallback
envelope through the model `write()` overlay. Requeues clear any stale failure payload.

Addon version is now `18.0.10.8.0` because `odoo.ai.turn` gains the stored `failure_payload` field.

## Deterministic validation actually executed for P2.3

Available Python validation:

```text
syntax compilation of exact proposed P2.3 Python files
PASS

isolated dependency-light P2.3 contract harness
5 passed in 0.05s
```

The harness used the exact P2.3 terminal/model/test sources plus a compatible P2.1
`FailureEnvelope` stub. It is supporting deterministic evidence only; it is **not** a substitute for
loading the actual Odoo model registry/database schema.

Added but not executed here:

```text
addons/odoo_ai_assistant/tests/test_turn_failure.py
addons/odoo_ai_assistant/tests/test_turn_queue.py
```

No GitHub Actions were used.

## Hard validation debt

```text
P2.3-ODOO-UPDATE
  gate_type: HARD
  origin_slice: P2.3-turn-failure-persistence
  commit_materially_tested: pending; must include 00d963e0bdf1a14efe55fb974c2642de038313ee
  downstream_scope_blocked: later Phase 2 browser/presentation consumer work
  reason: prove addon 18.0.10.8.0 creates/loads failure_payload cleanly on Odoo 18

P2.3-ODOO-FAILURE
  gate_type: HARD
  origin_slice: P2.3-turn-failure-persistence
  commit_materially_tested: pending; must include 00d963e0bdf1a14efe55fb974c2642de038313ee
  downstream_scope_blocked: later Phase 2 browser/presentation consumer work
  reason: run test_turn_failure.py + test_turn_queue.py with 0 failures/errors
```

Phase 2 real presentation gates remain pending:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

These are not cleared by the P2.3 dependency-light harness.

## Retained Phase 1 real-environment evidence

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
P1-REAL-TOOLCALL | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
P1-REAL-CANCEL   | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

## Invariants carried through P2.3

- Odoo remains operational and persistence authority.
- Business capabilities execute with the effective user and `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider facts are bounded and advisory; the host owns effect certainty.
- Existing queue retry policy still uses the stable `error_code`; P2.3 does not add retries.
- The durable write barrier and `recovery_required` remain authoritative once effects are possible.
- A write-barrier terminal failure is never presented as effect-free or retry-safe.
- Raw provider text, credentials, prompts and unrestricted tool payloads remain private.
- Browser projection revalidates persisted envelopes and fails closed on corrupt/mismatched payloads.
- No GitHub Actions are available for roadmap execution or validation.

## Exact next action

Do **not** start P2.4 or Phase 3 yet.

Run the P2.3 Odoo 18 validation gate on the exact implementation checkpoint:

```text
1. install/update addon version 18.0.10.8.0 on a disposable Odoo 18 database;
2. run addons/odoo_ai_assistant/tests/test_turn_failure.py;
3. run addons/odoo_ai_assistant/tests/test_turn_queue.py;
4. require 0 failures and 0 errors;
5. record the exact tested SHA and environment evidence.
```

If both P2.3 gates pass, mark the slice `COMPLETE` and select the next Phase 2 failure-browser slice.
If either fails, repair P2.3 first.
