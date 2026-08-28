# Unified agent runtime

The current product runtime is a single Odoo-owned, host-authorized agent loop embedded in the
`odoo_ai_assistant` addon. It supersedes the old rigid workflow router and, after ADR-019,
also supersedes the monolithic provider-owned tool loop as the active product path.

This document describes the implemented runtime contract. The broader target evolution — dynamic
context/evidence, Skills, multi-step effects, technical host capabilities, multiple providers and
non-blocking multi-chat product behavior — is defined in `PRODUCT_VISION.md` and the gated
`research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`; those target features are not implementation
claims here.

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

The provider-neutral `NextDecision` remains a strict three-branch union. At the Codex boundary the
adapter wraps that union below an object field and carries open capability arguments as bounded
JSON text because App Server Structured Outputs rejects root unions and open object properties.
The adapter decodes that transport envelope and then runs the unchanged strict decision parser and
host validation. Terminal provider failures retain only bounded machine facts (provider category,
optional HTTP status and optional upstream code); raw upstream messages and additional details are
not retained. Provider schema failures keep the sanitized `codex_output_schema_invalid` diagnostic.
An explicit `serverOverloaded` terminal category may additionally carry an advisory
`provider_retryable=True` flag, but only at this effect-free one-decision boundary. The adapter does
not retry provider requests itself and the hint grants no authority to repeat capabilities or
writes.

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

One host-validated `plan_step_proposal` is the canonical action proposal in the current runtime.
It is intentionally a current limitation, not the final product target: the evolution roadmap
replaces this with a bounded multi-step `EffectPlan` only after the existing P2-P4 foundation is
accepted and the new effect semantics receive their own hard gates.

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

The current runtime may still terminate an executed plan with host-generated completion text.
Post-effect provider continuation and natural synthesis are explicitly scheduled in Product Phase 5;
until that gate is implemented and validated, they are not current behavior.

## Persistence projections

Private `working_items_payload` and public `odoo.ai.turn.event` are deliberately separate. The
private transcript may contain bounded arguments/results required for provider continuation.
Browser/public events and diagnostics do not automatically expose them, raw prompts, credentials,
stdout/stderr or private reasoning.

Phase 3/4 look-ahead code additionally persists a separate bounded live projection for public
activity and provisional answer deltas. That implementation exists on `main`, but it remains subject
to the ordered real-environment acceptance recorded in `research/EXECUTION_STATE.md`.

## Concurrency boundary

A durable turn is server-side work and must not be treated as a global UI lock. The current queue
already uses lease-based claims and `FOR UPDATE SKIP LOCKED`, with two configured cron runner slots,
so distinct queued turns can be claimed concurrently within current bounded capacity.

The current browser still has global `state.loading` coupling that disables composer/history/model/
autonomy controls while one request is active. That is a known current limitation, not a desired
runtime invariant. Product Phase 5 replaces it with per-turn/per-conversation state and configurable
server capacity/backpressure. A running turn keeps its captured model/policy/context snapshot;
changing UI settings affects subsequent turns rather than mutating an in-flight turn.

## Compatibility

The previous `CodexReasoningEngine.run_agent_turn()` remains installed only as the bounded ADR-019
rollback seam pending an explicit cleanup slice. It is not the active embedded product composition.
The Odoo RPC boundary, account lifecycle from ADR-018 and existing approval/recovery authority remain
unchanged while the product UX evolves.

## Current validation status

Phase 0 and Phase 1 are formally complete with their recorded real Odoo 18 + authenticated Codex
evidence. Phase 2 implementation is present but remains blocked on its five mandatory real browser/
product-path failure-presentation gates.

Phase 3 public activity and Phase 4 provisional answer streaming implementation have also landed as
bounded look-ahead. Their acceptance is deliberately ordered and cannot be counted before upstream
gates:

```text
P2 five real gates PASS
  -> P3 four real gates PASS
      -> P4 four real gates PASS
          -> Product Phase 5 may start
```

Therefore code presence does not mean P3/P4 are complete. The exact gate IDs, tested SHAs and next
action are maintained in `docs/research/EXECUTION_STATE.md`, with reproducible procedures in
`PHASE23_REAL_VALIDATION_RUNBOOK.md` and `PHASE34_REAL_VALIDATION_RUNBOOK.md`.
