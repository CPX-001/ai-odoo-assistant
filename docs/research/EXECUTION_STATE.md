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
active_slice: P2.1-failure-envelope-schema
active_slice_state: COMPLETE
current_gate_type: DETERMINISTIC
blocking_validations: none
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: P2.2-codex-error-normalization
```

Phase 0 and Phase 1 are complete. Phase 2 has started. P2.1 defines and deterministically validates the bounded host-owned `FailureEnvelope` contract but does not yet wire it into provider normalization, turn persistence or browser projection.

## Phase 2 entry checkpoint

This run reconstructed remote `main` at:

```text
33ca2bfaeebb85f0675594b27c6d52cbd7bc8dcf
```

No newer regression evidence or validation debt blocked Phase 2. The Phase 1 close-out already records all required provider-boundary real-environment gates as PASS.

The current failure path was inspected before implementation:

```text
turn_queue.browser_status       -> error_code only
turn_runtime._error             -> {ok:false,error:{code}}
assistant_panel_service         -> known code carried as Error(message)
assistant_panel_streaming       -> all thrown errors become service_unavailable
assistant_failure_messages      -> code-to-prose mapping in JS
```

That evidence matches the Phase 2 playbook: the product needs one structured failure contract before presentation copy or retry UX changes.

## P2.1 implementation

Added `addons/odoo_ai_assistant/runtime/agent/failure.py` with a strict fixed-shape `FailureEnvelope` contract:

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

The routing enums are bounded. `safe_details` accepts only bounded JSON data (4 KiB total, bounded depth/items/strings) and unknown top-level fields fail closed. This is a structural safety bound only; later host mapping code must still redact semantically sensitive values before constructing an envelope.

P2.1 deliberately does not modify runtime behavior, turn persistence, controller payloads, frontend error normalization, error prose or retry behavior.

## Deterministic validation actually executed

In an isolated dependency-light Python workspace containing the exact proposed P2.1 target files and repository-relative paths:

```text
python -m py_compile \
  addons/odoo_ai_assistant/runtime/agent/failure.py \
  tests/unit/test_failure_envelope_contract.py
PASS

python -m pytest -q tests/unit/test_failure_envelope_contract.py
5 passed, 17 subtests passed
```

No GitHub Actions were used. A full repository/Odoo suite was not executed here and is not being reported as PASS.

## Phase 1 retained real-environment evidence

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
P1-REAL-TOOLCALL | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
P1-REAL-CANCEL   | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

The final Phase 1 live checkpoint used Odoo 18.0 Community through the normal HTTP -> persisted turn -> cron -> embedded runtime path. Sanitized evidence remains under `docs/research/evidence/phase1/2026-08-27/`.

## Validation debt

```text
Phase 1 mandatory validation debt: none
P2.1 mandatory validation debt: none
Phase 2 real presentation gates: pending until later slices make them materially testable
look-ahead slices consumed: 0
stacked unvalidated contract layers: 0
```

P2.2 consumes the deterministically validated P2.1 schema and therefore may start on the next independent run. Phase 3 remains blocked until the Phase 2 failure semantics it would consume are validated.

## Invariants carried through P2.1

- Odoo remains operational and persistence authority.
- Business capabilities execute with the effective user and `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- The provider proposes; the host validates and owns all effects.
- Preserved provider facts and retryability metadata remain bounded and advisory only.
- Raw provider messages/details, credentials, prompts and unrestricted tool payloads remain private.
- No provider/capability/write retry is introduced by P2.1.
- The durable write barrier and `recovery_required` semantics remain authoritative.
- No GitHub Actions are available for roadmap execution or validation.

## Exact next action

Re-inspect the exact new `main`, then implement only `P2.2-codex-error-normalization`. Map current sanitized `CodexDecisionError`/host terminal facts into `FailureEnvelope` with deterministic tests and explicit effect-state derivation. Do not yet persist/project the envelope to the browser, rewrite UI copy, add automatic retries, or begin Phase 3 public activity.
