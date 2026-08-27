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
active_slice: P2.2-codex-error-normalization
active_slice_state: COMPLETE
current_gate_type: DETERMINISTIC
blocking_validations: none
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: P2.3-turn-failure-persistence
```

Phase 0 and Phase 1 are complete. Phase 2 has completed its schema and provider-normalization
slices, but the envelope is not yet persisted on `odoo.ai.turn` or exposed to the browser.

## Current remote checkpoint inspected

P2.2 reconstructed `main` at:

```text
70d424cb52c456009fbc704bd8d00112436636b0
```

No newer commit or validation debt blocked the slice.

## Phase 2 progress

### P2.1 — FailureEnvelope schema

`COMPLETE`.

The host-owned contract remains:

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

The fixed shape, routing enums and bounded JSON/detail rules remain unchanged.

### P2.2 — Codex/provider error normalization

`COMPLETE`.

The active composition is now conceptually:

```text
CodexDecisionEngine
  -> FailureNormalizingDecisionEngine
      -> normalize_provider_failure(...)
      -> ProviderFailureError
          code = original sanitized product code
          failure = validated FailureEnvelope
  -> AgentTurnService
```

The wrapper is located at the provider/host decision boundary. It uses `effect_state=none`
explicitly because this wrapped call occurs before effectful plan execution and the durable write
barrier. A resumed authorized plan bypasses the provider decision path.

Known sanitized provider facts may now survive in the in-memory envelope:

```text
provider category
bounded HTTP status
bounded upstream code
advisory provider_retryable
```

Raw provider messages, stderr/stdout, prompts, request bodies, credentials and unrestricted payloads
are never read by the normalizer.

`serverOverloaded` becomes `retryability=safe` only when the provider already marked the failure
retryable and the host effect state is `none` or `not_started`. No retry is performed.

## Deterministic validation actually executed for P2.2

In an isolated dependency-light workspace containing the exact proposed target files:

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

A lightweight runtime-stub execution of the provider decorator also passed for an effect-safe
`serverOverloaded` error.

No GitHub Actions were used. No full repository/Odoo/Codex battery is being claimed for this slice.

## Retained Phase 1 real-environment evidence

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
P1-REAL-TOOLCALL | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
P1-REAL-CANCEL   | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

## Validation debt

```text
Phase 1 mandatory validation debt: none
P2.1 mandatory validation debt: none
P2.2 mandatory validation debt: none
Phase 2 real presentation gates: pending until envelope persistence/browser projection exists
look-ahead slices consumed: 0
stacked unvalidated contract layers: 0
```

Phase 3 remains blocked. P2.3 may start because it consumes the deterministically validated
P2.1/P2.2 contract and is the required next layer of the same Phase 2 failure path.

## Invariants carried through P2.2

- Odoo remains operational and persistence authority.
- Business capabilities execute with the effective user and `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- The provider proposes; the host validates and owns all effects.
- Preview, policy, approval, write barrier, execution and verification are unchanged.
- Preserved provider facts remain bounded and advisory.
- No provider/capability/write retry has been introduced.
- `recovery_required` and the durable write barrier remain authoritative once effects are possible.
- Raw provider text, credentials, prompts and unrestricted tool payloads remain private.
- No GitHub Actions are available for roadmap execution or validation.

## Exact next action

Re-inspect the new `main`, then implement only `P2.3-turn-failure-persistence`.

Persist a validated `FailureEnvelope` for terminal turn failures and return it from
`browser_status()` while preserving the existing `error_code` compatibility field. Derive
`effect_state` from authoritative queue/write-barrier state when effects may have started. Do not
yet rewrite frontend prose, add retry buttons/automatic retries, or begin Phase 3 public activity.
