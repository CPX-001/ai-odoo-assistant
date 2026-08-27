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
active_slice: P2.4-browser-failure-presentation
active_slice_record: not yet created
active_slice_state: READY
current_gate_type: NONE_FOR_READY_SLICE
blocking_validations: none
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: P2.4-browser-failure-presentation
```

Phase 0 and Phase 1 are complete. Phase 2 has implemented its schema, provider normalization and
terminal turn persistence slices. P2.3 is `COMPLETE` after real Odoo 18 validation and repair of a
failure-envelope overwrite discovered by the focused integration gate. The next coherent work is the
browser consumer/presentation slice; Phase 3 and Phase 4 are not yet eligible.

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

The exact repaired checkpoint materially validated on Odoo 18 is:

```text
8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
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

`COMPLETE`.

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

## Validation actually executed for P2.3

Deterministic Python validation on the repaired checkpoint:

```text
tests/unit
201 passed

full tests collection
344 passed, 36 explicit legacy/opt-in skips

focused dependency-light E2E contracts
29 passed

syntax compilation and git diff checks
PASS
```

Real Odoo 18 validation on a disposable database:

```text
addon install/update
PASS

TestAssistantTurnFailurePersistence
3 tests, 5 executions, 0 failed, 0 errors

TestAssistantTurnQueue
9 tests, 11 executions, 0 failed, 0 errors

full addon battery
95 tests, 131 executions, 0 failed, 0 errors

HOOT desktop @odoo_ai_assistant
78 passed, 0 failed
```

The first focused failure run exposed an overwrite bug: a later event-sequence update replaced a
carried provider envelope with a generic fallback. The repaired model only synthesizes fallback
payloads on terminal/error transitions or when no payload exists. The complete gates above were then
rerun against the repaired code.

Sanitized evidence:

```text
docs/research/evidence/phase2/2026-08-28/P2.3-ODOO-VALIDATION-8683ef6.md
```

No GitHub Actions were used.

## Closed P2.3 hard validation debt

```text
P2.3-ODOO-UPDATE  | PASS | 8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
P2.3-ODOO-FAILURE | PASS | 8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
```

Phase 2 real presentation gates remain pending:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

These are not cleared by storage/addon/HOOT tests. They become materially applicable only after
P2.4 consumes the structured failure in the browser and defines retry/presentation behavior.

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

Create the P2.4 slice record and implement only the browser failure consumer/presentation layer:

```text
1. parse and validate browser_status().failure without trusting arbitrary browser input;
2. preserve distinct category, retryability, effect_state and user_action behavior;
3. remove the streaming catch-all that flattens unknown failures to service_unavailable;
4. drive retry affordances from retryability/effect authority;
5. add focused HOOT and Odoo projection coverage;
6. run all five P2-REAL-* gates on real Odoo 18 + Codex.
```

Do not start Phase 3 until the Phase 2 exit criteria and real presentation gates pass. Phase 4 is
therefore not enabled: Phase 3 public activity has not been implemented or validated.
