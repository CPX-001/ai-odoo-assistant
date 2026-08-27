# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 1
phase_name: provider boundary stabilization
phase_state: IN_PROGRESS
active_phase_record: docs/research/PHASE1_PROVIDER_BOUNDARY.md
active_slice: P1.1-conformance-rebase
active_slice_state: COMPLETE
current_gate_type: NONE
next_slice: P1.2-current-adapter-conformance-binding
```

Phase 0 is complete. The exact implementation/test SHA
`9f832af4d6b1e6b74659bcd30aab21db481fd4b9` passed the real Odoo 18 + Codex + browser HELLO,
READ and strict ACTION gate; the docs-only close-out is `9cf9a8d3553cf8bc5a0b39ada63f2fba1c5f21ae`.

## New evidence processed

The latest committed evidence was processed before selecting Phase 1 work:

- `docs/research/evidence/phase0/2026-08-27/E2E-REAL-ENV-result-9f832af.md`: PASS;
- `docs/research/E2E_REAL_ENV_HANDOFF.md`: `REAL_ENV_VALIDATION_PASSED`;
- aggregate Phase 0 result: `ready_for_phase1=true`.

Earlier failed evidence remains historical and does not reopen Phase 0.

## P1.1 published content

The first Phase 1 slice reconciles the pre-convergence conformance preparation with the validated
E2E host-loop architecture.

The prepared v1 harness assumed provider-side dynamic tool calls. Current authoritative code instead
uses `CodexDecisionEngine.next_decision()` with provider-side tools disabled; Odoo validates each
`NextDecision` and owns capability execution. P1.1 therefore:

- advances the conformance contract to v2;
- replaces provider-side tool-execution cases with reasoning-decision, plan-proposal and final-answer
  mapping cases;
- adds the minimum structural `ReasoningProvider` port consumed conceptually by the current host:
  `next_decision(...) -> NextDecision`;
- keeps the current custom adapter unchanged;
- adds a dependency-light signature regression between the new port and
  `CodexDecisionEngine.next_decision`.

No provider implementation choice is made in this slice.

## Tests actually executed

```text
python -m pytest -q tests/unit/test_codex_provider_conformance.py
5 passed in 0.08s

python -m py_compile \
  tests/contracts/codex_provider_conformance.py \
  addons/odoo_ai_assistant/runtime/agent/provider.py
PASS
```

These checks were executed in the available reconstructed connector-backed mirror of the exact
changed files and current adapter signature.

## Tests not executed

- Odoo test suite: not required for this contract-only slice and unavailable through the GitHub
  connector execution path.
- Real Codex App Server conformance: intentionally deferred to P1.2.
- Browser/product-path validation: not required because active runtime behavior is unchanged.

## Remaining validation debt

All Phase 0 mandatory hard debt is closed.

Phase 1 mandatory completion debt:

```text
P1-REAL-SOAK-100 | HARD | provider boundary | Phase 2+
P1-REAL-TOOLCALL | HARD | host/provider capability mapping | Phase 2+
P1-REAL-CANCEL   | HARD | provider turn identity/cancellation | Phase 2+
P1-REAL-VERSION  | HARD | supported Codex protocol/version | Phase 2+
```

These are not yet due for P1.1 because it changes no active adapter behavior. Any later
behavior-changing provider repair must attach the relevant exact-SHA validation debt before Phase 1
can complete.

## Exact next action

Execute `P1.2-current-adapter-conformance-binding`:

1. bind the current custom `CodexDecisionEngine` to the v2 conformance harness;
2. produce a sanitized actual pass/fail matrix without changing behavior to fit expectations;
3. identify the smallest failing compatibility/safety boundary;
4. only then select a repair such as benign unknown-notification tolerance, structured terminal
   failure preservation, overload classification or cancellation correction;
5. do not add an official SDK adapter or another provider yet.
