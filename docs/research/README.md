# Research and execution guidance

This directory contains living decision-support and implementation playbooks. Current code + accepted ADRs remain authority; these documents define execution order and evidence.

## Current execution documents

| Document | Purpose |
| --- | --- |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | Ordered stabilization roadmap. |
| `E2E_AGENT_LOOP_CONVERGENCE.md` | Host-owned Codex decision-loop convergence record. |
| `EXECUTION_STATE.md` | Persistent active cursor, blockers and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Slice/gate/look-ahead rules; no GitHub Actions as roadmap authority. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named real Odoo+Codex/browser acceptance gates. |
| `SLICE_TEMPLATE.md` | Atomic slice template. |
| `PHASE0_BASELINE.md` | Completed baseline record/evidence. |
| `PHASE1_PROVIDER_BOUNDARY.md` | Completed provider-boundary record/evidence. |
| `PHASE2_FAILURE_CONTRACT.md` | Phase 2 structured failure-contract record. |
| `P2.3_TURN_FAILURE_PERSISTENCE.md` | Completed terminal failure persistence slice. |
| `P2.4_BROWSER_FAILURE_PRESENTATION.md` | Implemented browser consumer/presentation; hard real gates pending. |
| `PHASE3_PUBLIC_ACTIVITY_PREPARATION.md` | Independent Phase 3 contracts/harness prepared while production Phase 3 remains blocked. |
| `PHASE23_REAL_VALIDATION_RUNBOOK.md` | Repeatable commands/fixtures for the nine P2/P3 real gates. |

## Recursive rule

```text
inspect current main
-> read EXECUTION_STATE
-> implement only eligible coherent slice
-> run only tests genuinely available
-> record unrun mandatory validation as debt
-> publish coherent checkpoint
```

If a hard state is `REAL_ENV_VALIDATION_REQUIRED`, dependent later-phase production work stops. Independent fixtures/contracts/test tooling may use bounded look-ahead when they do not consume the unvalidated contract.

## No GitHub Actions

Roadmap validation does not use GitHub Actions. Tests must run in an environment that actually has the required Odoo/Codex/browser stack; unavailable tests remain explicitly NOT RUN.

Research documents must start from current code, distinguish observed from proposed behavior, preserve Odoo/host authority, define exit gates, and never expose raw prompts/credentials/provider stdout-stderr/unrestricted tool payloads/private reasoning in evidence.
