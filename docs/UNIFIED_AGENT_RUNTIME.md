# Unified agent runtime

The current product runtime is a single Odoo-owned, host-authorized agent loop embedded in the
`odoo_ai_assistant` addon. It supersedes the old rigid workflow router and, after ADR-019,
also supersedes the monolithic provider-owned tool loop as the active product path.

## Active turn shape

```text
browser -> Odoo durable turn -> cron lease under originating user (su=False)
 -> effective CapabilityRegistry
 -> private bounded working transcript
 -> CodexDecisionEngine returns exactly one NextDecision
      final_answer
      reasoning_capability_call
      plan_step_proposal
 -> Odoo validates the decision against the effective catalog/schema
 -> REASONING: execute -> persist result/error -> ask Codex again
 -> PLAN: canonical stage-only proposal -> CapabilityPlanService.prepare
      -> preview/preconditions -> policy/approval
      -> durable write barrier -> execute -> verify -> verified receipt
 -> authoritative Odoo result/public events -> browser
```

`CapabilityDefinition` remains the atomic executable authority contract. The provider never gains
an Odoo Environment, cannot enable a disabled capability, and cannot turn an arbitrary method name,
SQL, Python, shell or sudo request into authority.

## Reads

REASONING capabilities execute only through `CapabilityExecutor` with
`ExecutionAuthority.REASONING`, in the effective user's current Odoo cursor/savepoint. Every
decision, call, bounded result/error and terminal answer is persisted in the private
`working_items_payload` transcript. Correctable pre-effect errors may be returned to the provider
within explicit decision/call/failure budgets. ACL/authority denial may be followed only by a final
explanation, not another business call.

On restart, a persisted pending call is closed as an interrupted call instead of blindly executing
the same `call_id` again. Provider thread/process persistence is never business durability.

## Canonical PLAN proposal

One host-validated `plan_step_proposal` is the canonical action proposal. The active path does not
require the provider to also serialize the same action in a later `plan=[]` result and does not use
provider dynamic staging tools.

A proposal is stage-only during reasoning. It becomes one `PlannedCapability` and is passed
directly to the existing `CapabilityPlanService.prepare`. Preparation performs authoritative
preview, current precondition binding and approval policy without invoking the write handler.

The write lifecycle remains:

```text
canonical proposal
 -> prepare / exact preview
 -> current policy / human approval when required
 -> revalidation of version, binding and preconditions
 -> durable write barrier
 -> execute with ExecutionAuthority.PLAN under effective user
 -> verify
 -> verified-effect receipt
```

The barrier implementation is unchanged and is committed immediately before the first effect. A
verified-effect receipt is written in the same Odoo transaction as the business effects,
verification result and completed plan. If that transaction is lost after the barrier, recovery is
required; the host never blindly retries an ambiguous effect.

## Persistence projections

Private `working_items_payload` and public `odoo.ai.turn.event` are deliberately separate. The
private transcript may contain bounded arguments/results required for provider continuation.
Browser/public events and diagnostics do not automatically expose them, raw prompts, credentials,
stdout/stderr or private reasoning.

## Compatibility

The previous `CodexReasoningEngine.run_agent_turn()` remains installed only as the ADR-019 rollback
seam while real Odoo/Codex validation is pending. It is not the active embedded product
composition. The Assistant UI, Odoo RPC boundary, account lifecycle from ADR-018 and the existing
approval UX remain unchanged.

## Current validation status

E2E-0 through E2E-4 are implemented with deterministic/local contract coverage available in the
implementation environment. Real Odoo 18 + authenticated Codex/browser validation is still
required and must not be inferred from local tests. See `docs/research/EXECUTION_STATE.md`.
