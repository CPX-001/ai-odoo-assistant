# ADR-019 — Host-owned iterative decision loop and canonical plan proposal

## Estado

Accepted

## Contexto

The embedded runtime established by ADR-016 and the capability authority of ADR-017 remain the
correct security/deployment foundation, but the current Codex adapter asks one provider turn to
perform discovery, callback tools, plan staging and final structured serialization. Real Phase 0
ACTION evidence showed that an effective PLAN catalog could be visible while the provider still
terminated with a read-only answer before any host-observed action proposal existed.

The convergence research in `docs/research/E2E_AGENT_LOOP_CONVERGENCE.md` compares that behavior
with mature host loops: one provider decision is validated by the host, its typed result is appended
to working context, and the provider is asked for the next decision. The Assistant already has
stronger Odoo authority and write safety than those references, so only orchestration should change.

## Decisión

Odoo owns the iterative decision loop for product turns.

A provider returns exactly one `NextDecision` at a time:

- `final_answer`;
- `reasoning_capability_call`;
- `plan_step_proposal`.

Odoo resolves every selected capability against the effective catalog and validates its schema.
REASONING calls may execute only through `CapabilityExecutor` under the effective user with
`su=False`. A PLAN proposal is stage-only and canonical once host-validated; it never invokes the
handler during reasoning and it is not duplicated in a later final `plan=[]` serialization.

The active turn owns a bounded private typed working transcript persisted in Odoo. It records only
the state required to continue/recover the host loop (decisions, calls, results/errors, proposal,
prepared plan and verified receipt). Public turn events remain a separate sanitized projection and
must not expose capability arguments/results, prompts, credentials or private reasoning.

The existing effect lifecycle is unchanged:

```text
canonical PLAN proposal
 -> CapabilityPlanService.prepare
 -> preview + preconditions
 -> policy / approval
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> receipt / recovery state
```

A provider restart reconstructs the next decision from Odoo state rather than relying on provider
thread persistence. A completed `call_id` is never executed twice; an ambiguous interrupted call is
represented explicitly and handled within bounded recovery rules. Post-write-barrier ambiguity
continues to use the ADR-016 recovery path rather than automatic retry.

ADR-018 remains unchanged: Codex credentials are provider-owned and installation-scoped while each
database has an explicit non-secret activation gate.

## Consecuencias

- the provider chooses the next requested operation, but Odoo owns sequencing and authority;
- capability results/errors become typed model input instead of flattened prose;
- provider turns may be disposable without losing active-turn progress;
- PLAN has one canonical representation at the host boundary;
- the current Assistant UI, queue, approval UX contract and persistence owner remain unchanged;
- no router, second agent runtime, service/sidecar, provider, API, RAG or generic ORM escape hatch is introduced.

## Rollback

Until the convergence is proven in the real Odoo/Codex environment, the legacy monolithic
`CodexReasoningEngine.run_agent_turn()` implementation may remain as a non-default compatibility
path. Rolling back the new host loop means switching the composition root back to that path; it does
not delete Odoo turn history, rewrite approved plans or replay effects. Any turn that crossed the
write barrier continues to follow existing verification/recovery semantics.

## Referencias

- `docs/adr/ADR-016-embedded-odoo-runtime.md`
- `docs/adr/ADR-017-addon-capability-framework.md`
- `docs/adr/ADR-018-database-scoped-codex-activation.md`
- `docs/research/E2E_AGENT_LOOP_CONVERGENCE.md`
