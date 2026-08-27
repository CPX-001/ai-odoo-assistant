# Current implementation state

Revalidated through the Phase 1 provider-boundary slices on 27 August 2026. The Phase 0 product
path and the P1.3 Codex version/100-turn soak have passed real Odoo 18 + authenticated Codex
validation. Phase 1 completion still requires `P1-REAL-TOOLCALL` and `P1-REAL-CANCEL`; the exact
cursor and validation debt are tracked in `docs/research/EXECUTION_STATE.md`.

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

Codex Structured Outputs uses an adapter-only object envelope: the three decision branches live in
a nested union and open capability arguments cross as bounded JSON text. The adapter decodes that
envelope before the unchanged strict `NextDecision` parser and host validation run. This avoids the
App Server rejection of root `oneOf` schemas without changing the provider-neutral contract.

For READ, only effective REASONING definitions execute and only through
`CapabilityExecutor(..., ExecutionAuthority.REASONING)`. Results/errors become bounded private
working items and are supplied to the next provider decision. Provider decisions, calls,
per-definition calls, correctable failures, result bytes and total transcript bytes are bounded.
Cancellation is checked before provider/capability work. Persisted pending call ids are not
blindly reexecuted after restart.

The Codex decision adapter tolerates only bounded inert unknown notifications while preserving
strict identity/critical-event checks. Terminal provider failures retain only bounded machine facts
(category, optional HTTP status and upstream code); raw provider messages/details are not retained.
Explicit `serverOverloaded` terminal facts are marked with an advisory `provider_retryable` hint only
at the effect-free one-decision boundary. The adapter does not retry provider calls itself, and this
classification does not weaken the existing durable write-barrier/recovery rules.

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

Dependency-light contract tests and Python compilation cover the current provider-boundary
slices. Real Odoo 18 Community + Codex 0.149.1 evidence has passed `P1-REAL-VERSION` and
`P1-REAL-SOAK-100` at the recorded P1.3 checkpoint, including 100/100 normal product-path turns.
The final Phase 1 provider checkpoint must still pass the independent `P1-REAL-TOOLCALL` and
`P1-REAL-CANCEL` gates before Phase 2 begins. Unexecuted Odoo/module-update tests remain explicit
validation debt rather than assumed passes.
