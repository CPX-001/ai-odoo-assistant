# Stabilization execution state

State format: 3
Updated: 2026-08-28
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 2
phase_name: structured failure contract
phase_state: READY
active_phase_record: NONE_CREATE_BEFORE_IMPLEMENTATION
active_slice: P2.1-failure-envelope-schema
active_slice_state: READY
current_gate_type: DETERMINISTIC
blocking_validations: none
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: P2.1-failure-envelope-schema
```

Phase 0 and Phase 1 are complete. Phase 2 has not started; `READY` means the next run must first
inspect current failure projections/browser contracts and create the atomic Phase 2 phase/slice
record before changing behavior.

## Phase 1 close-out checkpoint

The run reconstructed `origin/main` at `77853109f75ee1b7e43511ad7a15e450f43026bb`.
The full Odoo battery then exposed a stale test that bypassed the already-accepted database-scoped
Codex connection gate. The test-only repair uses the supported settings connect/logout actions and
was committed as:

```text
db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

No product runtime behavior changed in that checkpoint. The addon install/update, complete Odoo
battery and both final real-environment gates were executed against that exact checkout.

## Tests actually executed

Dependency-light validation:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_provider_conformance.py
8 passed

.venv/bin/python -m pytest -q tests/unit
184 passed

.venv/bin/python -m pytest -q \
  tests/e2e/test_e2e_convergence_battery.py \
  tests/e2e/test_e2e_decision_sequences.py \
  tests/e2e/test_next_decision_contract.py \
  tests/e2e/test_working_transcript_contract.py \
  tests/e2e/test_canonical_plan_proposal.py
29 passed

provider/contract Python compilation
PASS
```

Real Odoo 18 Community validation on a fresh disposable database:

```text
fresh addon install
PASS

explicit addon update
PASS

initial complete addon battery
1 stale test failed; 0 errors

focused repaired database-connection test
PASS

complete addon battery after repair
odoo_ai_assistant test stats: 126 executions
Odoo result: 0 failed, 0 errors of 92 tests
process exit: 0
```

No GitHub Actions were used.

## Phase 1 real-environment evidence

Previously cleared and retained:

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
```

Final completion gates on `db6e5c12c53e9a99ad3a55f7472eb13f93855a06`:

```text
P1-REAL-TOOLCALL | PASS
final state: completed
host capabilities: odoo.get_effective_schema, odoo.query_records
effective user: dedicated internal non-admin, su=false
fixture changed: false

P1-REAL-CANCEL | PASS
cancel response: cancel_requested
final state: cancelled
write barrier observed: false
fixture changed: false
provider subprocesses remaining: 0
subsequent distinct turn: completed
```

The final gates used Odoo 18.0 Community and the installed Codex CLI/App Server 0.144.2 through the
normal HTTP -> persisted turn -> cron -> embedded runtime path. Sanitized evidence is stored at
`docs/research/evidence/phase1/2026-08-27/P1-REAL-TOOLCALL-CANCEL-db6e5c1.md`.

## Validation debt

```text
Phase 1 mandatory validation debt: none
Phase 2 validation debt: none yet; phase has not started
look-ahead slices consumed: 0
stacked unvalidated contract layers: 0
```

No mandatory Phase 1 test remains unexecuted. Broader sidecar-era/legacy suites and frontend UX
work are outside the completed provider-boundary gate and were not used as substitutes for it.

## Invariants carried into Phase 2

- Odoo remains operational and persistence authority.
- Business capabilities execute with the effective user and `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- The provider proposes; the host validates and owns all effects.
- Preserved provider facts and retryability metadata remain bounded and advisory only.
- Raw provider messages/details, credentials, prompts and unrestricted tool payloads remain private.
- No provider/capability/write retry may be inferred from Phase 1 metadata alone.
- The durable write barrier and `recovery_required` semantics remain authoritative.
- No GitHub Actions are available for roadmap execution or validation.

## Exact next action

Create the Phase 2 phase/slice record from section 6 of
`FOUNDATION_STABILIZATION_PLAYBOOK.md`. Inspect the current backend turn errors and browser failure
projection, then implement only `P2.1-failure-envelope-schema`: one bounded structured
`FailureEnvelope` contract with deterministic validation. Do not yet rewrite UI copy, implement
public activity/answer streaming, or add automatic retries. Define the affected real validation IDs
before the slice leaves `READY`.
