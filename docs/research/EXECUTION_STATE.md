# Stabilization execution state

State format: 3
Updated: 2026-08-28
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

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

Phase 0 and Phase 1 are complete. P2.1/P2.2/P2.3 remain complete. P2.4 code and deterministic contract coverage are implemented at `1a643cd948b2a68c941863e6d6f411b968afd61f`; its five real presentation gates were not executable here and are the hard blocker.

## P2.4

`browser_status().failure` now passes through a strict browser `FailureEnvelope` mirror. Code/category/retry/effect/action/diagnostic/provider facts survive; invalid/tampered data fails closed. The streaming catch-all no longer universally maps bounded unknown errors to `service_unavailable`. Retry exists only for `safe + none/not_started + retry`; `partial`, `unknown` and `recovery_required` never offer blind replay. Presentation never renders raw `safe_details`, `safe_summary`, provider messages, prompts, credentials, stdout/stderr or private reasoning.

## Phase 2 hard validation debt

```text
P2-REAL-AUTH      | HARD | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-ACL       | HARD | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TIMEOUT   | HARD | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TOOLFAIL  | HARD | REAL_ENV_VALIDATION_REQUIRED
P2-REAL-RECOVERY  | HARD | REAL_ENV_VALIDATION_REQUIRED
```

Fixtures/commands: `tests/e2e/phase23_real_gates.json` and `PHASE23_REAL_VALIDATION_RUNBOOK.md`.

## Phase 3 look-ahead

Phase 3 production is not selected. Independent preparation only is recorded in `PHASE3_PUBLIC_ACTIVITY_PREPARATION.md`: closed Python/JS `PublicTurnEvent` parsers, bounded cursor/resource semantics, prohibition of `agent.thinking`, a trusted-code descriptor value not yet wired into `CapabilityDefinition`, and opt-in `phase3_real` acceptance tests. LIVE-VISIBILITY requires a second DB connection to observe a persisted event before the worker business transaction commits.

```text
P3-REAL-ACTIVITY-READ    | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-ACTIVITY-ACTION  | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-LIVE-VISIBILITY  | NOT RUN | BLOCKED_BY_PHASE2
P3-REAL-REDACTION        | NOT RUN | BLOCKED_BY_PHASE2
```

## Invariants

Odoo/persistence authority, effective-user `su=False`, `CapabilityDefinition`, approval/write barrier/verification remain unchanged. No sidecar, parallel tool registry or arbitrary SQL/Python/shell/sudo/unrestricted Odoo method surface was introduced. Public activity preparation has no arbitrary payload or chain-of-thought event.

## Next action

Run the five P2 gates on disposable Odoo 18 using the runbook. Repair and rerun any failed gate. Only after all five PASS may Phase 2 become COMPLETE and Phase 3 production be selected. Phase 4 is `NOT_READY`.
