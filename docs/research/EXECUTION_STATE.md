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
active_slice_record: docs/research/P2.4_BROWSER_FAILURE_PRESENTATION.md
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD_REAL_ENV
blocking_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: NONE_UNTIL_PHASE2_REAL_GATES_PASS
```

Phase 0 and Phase 1 are complete. Phase 2 has implemented its schema, provider normalization, terminal turn persistence and browser consumer/presentation slices. P2.3 is `COMPLETE` after real Odoo 18 validation and repair of a failure-envelope overwrite discovered by the focused integration gate. P2.4 code and deterministic contracts are implemented, but its five real presentation gates were not executable in the publishing environment and are now the hard blocker. Phase 3 production and Phase 4 are not eligible.

The `Next action` prose at the end of the historical P2.3 section in `PHASE2_FAILURE_CONTRACT.md` is superseded by this cursor and `P2.4_BROWSER_FAILURE_PRESENTATION.md`.

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

The active provider boundary preserves sanitized provider category, bounded HTTP status, bounded upstream code and advisory retryability inside a validated `FailureEnvelope`. Raw provider text, credentials, stdout/stderr, prompts and unrestricted payloads are not copied.

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

`models/turn_failure.py` preserves the original queue retry/failure state machine for ordinary errors. A specialized finalizer is used only when the exception already carries a validated provider envelope so P2.2 facts survive atomically. Generic terminal writes receive a bounded host fallback envelope through the model `write()` overlay. Requeues clear any stale failure payload.

P2.3 addon version was `18.0.10.8.0` because `odoo.ai.turn` gained the stored `failure_payload` field.

### P2.4 — browser failure presentation

`REAL_ENV_VALIDATION_REQUIRED`.

Material behavior was implemented at `1a643cd948b2a68c941863e6d6f411b968afd61f`; later descendants only repaired validation tooling/documentation/style unless separately recorded.

```text
browser_status().failure
  -> exact bounded browser parser
  -> structured AssistantFailureError
  -> streaming/polling state.failure
  -> deterministic failure presentation
  -> retry only if safe + effect-free/not-started + action=retry
```

The browser parser rejects malformed/mismatched envelopes, unknown top-level keys, oversized detail data and secret-bearing detail keys. Presentation uses the machine category/effect/action but does not display `safe_summary`, `safe_details`, provider text, prompts, credentials, stdout/stderr or private reasoning. Stable `error_code` remains a compatibility fallback.

A bounded unknown error code such as a controlled stream disconnect is preserved rather than universally replaced by `service_unavailable`. Free-form/unbounded exception messages still fail closed to a generic bounded code.

`partial`, `unknown` and `recovery_required` never expose blind replay. The existing write barrier remains effect-state authority.

Addon version is now `18.0.10.9.0`.

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

The first focused failure run exposed an overwrite bug: a later event-sequence update replaced a carried provider envelope with a generic fallback. The repaired model only synthesizes fallback payloads on terminal/error transitions or when no payload exists. The complete gates above were then rerun against the repaired code.

Sanitized evidence:

```text
docs/research/evidence/phase2/2026-08-28/P2.3-ODOO-VALIDATION-8683ef6.md
```

No GitHub Actions were used.

## P2.4 deterministic preparation actually executed

In the isolated publishing environment, before the GitHub checkpoint was assembled, the prepared P2.4/Phase 3-independent sources executed:

```text
node --check on prepared P2.4/Phase3 JS sources/tests
PASS

XML parse of assistant_failure_presentation.xml
PASS

node tests/js/failure_contract_test.mjs
failure contract: 7 assertions passed

node tests/js/public_activity_contract_test.mjs
public activity contract: 5 assertions passed

python tests/e2e/phase23_real_gate_check.py
phase23 real-gate manifest: 9 definitions valid

focused dependency-light pytest
6 passed

Python py_compile of prepared contracts/runners/Odoo test sources
PASS
```

These were not Odoo/HOOT/product-path tests. The later published Git descendants were reviewed and the remote fast-forward was verified, but no local checkout of the final Git tree was available for a literal final-tree rerun. Therefore this evidence is deterministic preparation, not a substitute for the mandatory real gate.

## Closed P2.3 hard validation debt

```text
P2.3-ODOO-UPDATE  | PASS | 8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
P2.3-ODOO-FAILURE | PASS | 8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
```

## Open Phase 2 hard validation debt

```text
P2-REAL-AUTH      | HARD | P2.4 | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-ACL       | HARD | P2.4 | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TIMEOUT   | HARD | P2.4 | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TOOLFAIL  | HARD | P2.4 | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-RECOVERY  | HARD | P2.4 | REAL_ENV_VALIDATION_REQUIRED
```

Fixtures, expected backend/browser behavior, cleanup and commands are recorded in:

```text
tests/e2e/phase23_real_gates.json
docs/research/PHASE23_REAL_VALIDATION_RUNBOOK.md
```

Backend fixture success alone does not close a real presentation gate. Each gate needs the real Odoo 18/browser observation and sanitized evidence for the exact tested SHA.

## Phase 3 bounded look-ahead

Production Phase 3 is **not selected**. The hard dependency from failure semantics to public activity prevents implementation of a second unvalidated product contract layer.

Independent preparation only is recorded in `PHASE3_PUBLIC_ACTIVITY_PREPARATION.md`:

- closed dependency-light Python and browser `PublicTurnEvent` contracts;
- closed kind/phase/status catalogs and bounded resources;
- strict cursor ordering/reconnect batch validation;
- explicit `agent.thinking` rejection and no arbitrary payload field;
- trusted-code public activity descriptor value prepared but not wired into `CapabilityDefinition`;
- opt-in `phase3_real` READ/ACTION/LIVE-VISIBILITY/REDACTION acceptance tests.

The LIVE-VISIBILITY harness uses a second database connection and requires a public event to be visible before the worker business cursor commits. It does not use browser timers as liveness evidence.

```text
P3-REAL-ACTIVITY-READ    | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-ACTIVITY-ACTION  | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-LIVE-VISIBILITY  | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-REDACTION        | NOT RUN | BLOCKED_BY_PHASE2
```

## Retained Phase 1 real-environment evidence

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
P1-REAL-TOOLCALL | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
P1-REAL-CANCEL   | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

## Invariants carried through P2.4

- Odoo remains operational and persistence authority.
- Business capabilities execute with the effective user and `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider facts are bounded and advisory; the host owns effect certainty.
- Existing queue/write recovery remains host-controlled; P2.4 does not authorize business retries.
- The durable write barrier and `recovery_required` remain authoritative once effects are possible.
- A write-barrier terminal failure is never presented as effect-free or retry-safe.
- Raw provider text, credentials, prompts, stdout/stderr, unrestricted tool payloads and private reasoning remain non-public.
- Browser failure projection fails closed on corrupt/mismatched payloads.
- No sidecar, parallel tool registry, arbitrary SQL/Python/shell/sudo or unrestricted ORM method surface was introduced.
- No GitHub Actions are used for roadmap execution or validation.

## Exact next action

Run the five P2 real gates on disposable Odoo 18 using `PHASE23_REAL_VALIDATION_RUNBOOK.md`:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

If any gate fails, repair P2.4, add regression coverage and rerun that exact gate. Only after all five pass may P2.4 and Phase 2 become `COMPLETE`, Phase 3 production be selected, and its four real gates become eligible. Phase 4 remains `NOT_READY`.
