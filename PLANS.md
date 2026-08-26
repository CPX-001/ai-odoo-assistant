# Execution plans

Use an ExecPlan for substantial work that benefits from an explicit inspected baseline, invariants, phases and verification. The plan is a working engineering artifact, not a substitute for current code/ADRs.

## Start from the current repository

Every plan must record the inspected `main` commit and relevant current sources before proposing architecture. Use this authority order:

1. current code + accepted ADRs;
2. current docs indexed by `docs/README.md`;
3. current tests;
4. historical task packets/reports/research snapshots;
5. external references.

Do not copy assumptions from old `docs/codex/exec-plans/`: those plans are historical examples and may refer to the retired sidecar.

## Required plan sections

A useful plan should contain:

### Problem and outcome

What concrete product/engineering problem exists, what behavior should change, and what observable result proves it is solved.

### Inspected baseline

Commit SHA, relevant modules/classes/models/docs/tests and any contradictions found. State clearly which behavior is implemented versus roadmap-only.

### Invariants and failure modes

List security/authority/deployment constraints that must remain true. For this project, explicitly consider Odoo effective-user authority, capability host validation, durable turns, write approval/verification and untrusted retrieval data when relevant.

### References and alternatives

If a subsystem has already been studied in the Project PDFs or external projects, identify the exact pattern that helps and what will **not** be copied. A framework/reference is not a requirement.

### Implementation phases

Use phases that leave the repository coherent. Reuse existing `AgentTurnService`, queue/events, capability registry/executor and Odoo configuration before adding parallel infrastructure.

### Verification

Specify deterministic tests, Odoo integration/E2E checks and agentic evals when behavior depends on model selection/reasoning. For writes include preview/approval/stale preconditions/verification/recovery.

### Documentation and cleanup

Name current docs that will change. Remove or explicitly classify obsolete current-path code/doc claims; do not rewrite historical evidence as if it were current.

## Progress discipline

Update the plan as facts change. Record discoveries and decisions. If implementation reveals that the proposed architecture is wrong, revise the plan instead of forcing the original design.

Do not declare a phase complete because code was written: tests/evals, integration behavior, documentation and repository coherence are part of completion.

## Git

Work directly on `main` unless the user explicitly requests a branch or pull request. Re-check HEAD before writes so concurrent changes are not overwritten.