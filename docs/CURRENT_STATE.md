# Current implementation state

Revalidated against the E2E-4 implementation checkpoint on 27 August 2026. Real Odoo 18 +
authenticated Codex validation remains pending and is tracked in
`docs/research/EXECUTION_STATE.md`.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Installable product: `addons/odoo_ai_assistant`, version `18.0.10.7.0`.
- Runtime: embedded in Odoo; browser uses Odoo RPC only.
- Durable work: `odoo.ai.turn`, native `ir.cron`, private working transcript and sanitized events.
- Business authority: originating effective Odoo user with `su=False`.
- Reasoning provider: local Codex App Server subprocess; provider credentials stay provider-owned.

## Active host loop

ADR-019 is the active orchestration path. `CodexDecisionEngine` returns exactly one strict
`NextDecision` per provider call. `AgentTurnService` resolves every selected capability against the
effective registry and validates its arguments host-side.

For READ, only effective REASONING definitions execute and only through
`CapabilityExecutor(..., ExecutionAuthority.REASONING)`. Results/errors become bounded private
working items and are supplied to the next provider decision. Provider decisions, calls,
per-definition calls, correctable failures, result bytes and total transcript bytes are bounded.
Cancellation is checked before provider/capability work. Persisted pending call ids are not
blindly reexecuted after restart.

## Canonical actions

A validated `PlanStepProposal` is now the one canonical PLAN representation in the active path.
It is stage-only during reasoning and is converted to one `PlannedCapability`; no PLAN handler is
invoked there. The proposal feeds the existing `CapabilityPlanService.prepare` lifecycle directly.

Preparation performs the real preview/precondition binding and policy decision. If approval is
required, the record remains unchanged and the turn enters `awaiting_confirmation`. Approval
requeues the same bound turn. Execution revalidates version/binding/preconditions/current policy,
crosses the unchanged durable write barrier immediately before the first effect, executes under the
effective user, verifies, and records a private verified-effect receipt.

Business effects, completed plan data, verification and verified receipt use the same current Odoo
transaction. If that transaction is lost after the separately committed write barrier, existing
recovery semantics apply and no blind retry occurs.

## Capability authority

`CapabilityDefinition` remains the atomic contract and `CapabilityRegistry` remains the effective
catalog authority. ACLs, record rules, field permissions, active companies, schemas, enablement,
risk and approval remain host/Odoo-owned. No generic arbitrary SQL, Python, shell, sudo, network
escape hatch or unrestricted ORM method surface has been added.

Current core providers remain `odoo_query`, `odoo_actions`, `odoo_batch` and `odoo_runtime`.
External `CapabilityProvider`, configurable Skill/Bundle composition and general embedded RAG are
still future work, not implementation claims.

## Persistence and UI

`working_items_payload` is private active-turn state. `odoo.ai.turn.event` and normal result payloads
are sanitized projections for the existing interface. The panel/interface has not been redesigned.

The legacy monolithic Codex adapter remains a non-default ADR-019 rollback seam only. The active
product path uses the host-owned decision loop.

## Validation status

Local dependency-light contract tests and Python compilation were executed for the convergence
slices. Odoo TransactionCase/module-update tests and real Odoo+Codex/browser tests that cannot run
in the current environment remain explicit validation debt. No real-environment PASS is claimed.
