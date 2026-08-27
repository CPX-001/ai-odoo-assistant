# Phase 1 — provider boundary stabilization

Date: 2026-08-27  
Inspected main: `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`  
Status: `IN_PROGRESS`

## Goal

Stabilize the Codex provider boundary around the Odoo-owned host loop before changing failure
semantics, public activity, answer streaming or chat UX.

The validated Phase 0 architecture is authoritative:

```text
Codex proposes one NextDecision
  -> Odoo validates the decision
  -> Odoo executes REASONING capabilities with the effective user and su=False
  -> PLAN proposals remain stage-only
  -> Odoo owns preview, policy, approval, write barrier, execution and verification
```

Provider-side dynamic tool execution from the pre-convergence playbook is therefore no longer a
valid target contract.

## P1.1 — conformance rebase and minimum provider port

State: `COMPLETE`

Objective:

- rebase the prepared Codex conformance manifest onto the validated one-decision host loop;
- define the smallest provider-neutral port the current host actually needs;
- preserve the existing custom Codex adapter and all Odoo authority semantics;
- do not add another provider and do not choose SDK-vs-custom yet.

Changes:

- conformance format advances to v2;
- obsolete provider-side `dynamic_tool_mapping`, `capability_success` and `capability_failure`
  cases are replaced by `reasoning_decision_mapping`, `plan_decision_mapping` and
  `final_answer_mapping`;
- `ReasoningProvider` is the minimal structural port: one async `next_decision(...) -> NextDecision`;
- the port is exported without changing `AgentTurnService` runtime composition yet;
- a dependency-light AST regression proves the port signature matches the current
  `CodexDecisionEngine.next_decision` signature.

The remaining protocol cases continue to cover initialize, thread isolation, output schema,
agent-message events, unknown notifications, malformed critical events, identity mismatch,
cancellation, terminal failures and overload/backpressure.

## Deterministic validation

Actually executed against the reconstructed changed files:

```text
python -m pytest -q tests/unit/test_codex_provider_conformance.py
5 passed in 0.08s

python -m py_compile \
  tests/contracts/codex_provider_conformance.py \
  addons/odoo_ai_assistant/runtime/agent/provider.py
PASS
```

No Odoo, browser or live Codex validation was executed for P1.1. P1.1 changes contracts/tests and
introduces a structural protocol only; it does not change provider lifecycle or production turn
behavior.

## Invariants

- Odoo remains operational and persistence authority.
- Effective-user capability execution remains `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Provider output is untrusted and host-validated.
- PLAN remains proposal-only before the existing action lifecycle.
- No SQL/Python/shell/sudo/unrestricted ORM escape hatch is introduced.
- Codex credentials remain provider-owned.
- No provider, bundle or skill abstraction is introduced.

## Validation debt

Phase 1 mandatory real-environment debt remains open for later behavior-changing slices:

- `P1-REAL-SOAK-100` — HARD before Phase 1 completion;
- `P1-REAL-TOOLCALL` — HARD before Phase 1 completion;
- `P1-REAL-CANCEL` — HARD before Phase 1 completion;
- `P1-REAL-VERSION` — HARD before Phase 1 completion.

P1.1 itself creates no new real-environment debt because it does not change the active adapter
behavior.

## Exact next action

Bind the current custom `CodexDecisionEngine` to the v2 adapter-neutral conformance harness and
record the actual pass/fail matrix. Do not change forward-compatibility behavior merely to make the
suite green. The observed matrix must drive the smallest next repair slice, especially for unknown
benign notifications, terminal structured errors, overload/backpressure and cancellation.
