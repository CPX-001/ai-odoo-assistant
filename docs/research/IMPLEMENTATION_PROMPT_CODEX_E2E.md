# Implementation prompt — functional Codex E2E loop for Odoo 18

Use the prompt below in a fresh ChatGPT/Codex task opened at the repository root. It is intentionally
implementation-oriented and requires evidence rather than a large speculative rewrite.

---

You are working in the `ai-odoo-assistant` repository for Odoo 18. Implement the next coherent
slice of the E2E agent-loop convergence described in:

- `AGENTS.md` and every applicable nested `AGENTS.md`;
- `docs/README.md`;
- `docs/research/EXECUTION_STATE.md`;
- `docs/research/E2E_AGENT_LOOP_CONVERGENCE.md`;
- `docs/research/CONTINUOUS_EXECUTION_PROTOCOL.md`;
- accepted ADR-016, ADR-017 and ADR-018.

First inspect current `main`, the current implementation and tests. Do not rely on this prompt for
facts that the repository can answer. If `origin/main` advanced, fast-forward/reconcile safely
before editing. Preserve unrelated user changes.

## Product objective

Make the existing Assistant reliably complete hello, reads and safe Odoo actions through a bounded
host-owned loop inspired by Apexive/`odoo-llm`:

```text
Codex selects one next decision
-> Odoo validates and executes/stages it
-> Odoo appends a typed result
-> Codex receives the result and selects the next decision
-> repeat until final answer or authoritative action preview
```

Take only the mature control-loop behavior from Apexive. Do not replace the Assistant UI, durable
turns, capability framework or action lifecycle with Apexive models.

## Invariants that may not change

- Odoo is the sole durable business authority.
- Browser calls Odoo only; no browser-to-Codex or browser-to-sidecar path.
- Every capability is a `CapabilityDefinition` from the effective registry.
- Run under the originating effective Odoo user with `su=False`.
- Preserve ACLs, record rules, company scope, schemas, budgets and enablement.
- REASONING capabilities may execute during the loop.
- PLAN capabilities may only be proposed/staged during reasoning.
- Writes remain `prepare -> preview -> policy/approval -> durable barrier -> execute -> verify`.
- No arbitrary ORM method, SQL, Python, shell, sudo or approval bypass.
- No blind retry after the write barrier or ambiguous effect.
- No raw prompts, arguments/results, business values, credentials or private reasoning in public
  events, diagnostics, committed evidence or logs.
- Do not change the panel/interface or add provider/API/RAG/tool-selector work in this slice.
- Use the current Codex account/App Server integration only; do not require an API key.

## Required target contract

Introduce or converge on a provider-neutral strict union with exactly one branch per call:

```text
FinalAnswer(kind, answer, confidence)
ReasoningCapabilityCall(kind, call_id, capability, arguments)
PlanStepProposal(kind, call_id, capability, arguments, user_summary)
```

Capability identifiers and arguments are untrusted until the host resolves and validates them.
One validated `PlanStepProposal` is the canonical plan step. Do not require Codex to duplicate it
in a final `plan=[]` result. A final answer cannot execute or imply an unverified write.

Initially expose the complete effective catalog: every enabled/visible REASONING capability is
callable and every enabled/visible PLAN capability is proposable. “Complete” never bypasses
effective-user filtering or exposes arbitrary code/ORM execution.

## Persistence and execution order

Follow `E2E_AGENT_LOOP_CONVERGENCE.md`. Work persistently toward a functional E2E result, but
implement and validate only one coherent slice at a time. Commit/push each passed slice, update the
execution cursor, re-read current `main`, and then continue with the next authorized slice while a
safe local next step exists. Do not stop merely because E2E-0 added tests or E2E-1 added a
contract; the requested outcome is a passing real ACTION. The expected sequence is:

1. E2E-0 decision-sequence eval fixtures and budgets;
2. E2E-1 `NextDecision` contract plus one-decision Codex structured-output adapter;
3. E2E-2 durable typed working transcript;
4. E2E-3 host loop for READ;
5. E2E-4 canonical PLAN proposal through the existing action lifecycle.

Do not stack later slices on an unvalidated earlier contract. If the current execution cursor says
a previous slice is waiting for real evidence, run or request exactly that evidence before moving
on.

For the Codex transport, use the proven local `llm_codex` pattern as a behavioral reference: send
the bounded effective catalog and require one structured next decision. Do not copy its security,
sudo, mail-thread or generic tool-execution code. Keep App Server transport details isolated so
dynamic tools can be reconsidered only after conformance proves parity.

## Tests and evidence

Write failing tests first for the selected slice. At minimum cover:

- exactly one valid decision branch;
- unknown/disabled/inaccessible capability rejection;
- schema-invalid arguments with no execution;
- PLAN proposal never invokes its capability handler during reasoning;
- bounded correctable failure followed by a repaired call;
- loop/call/byte budgets and cancellation;
- duplicate `call_id` idempotency across worker restart;
- no public leakage of tool arguments/results;
- no regression in preview, approval, revalidation, barrier, execute, verify and recovery.

Use representative decision-sequence evals for hello, read, multi-read, patch, create, denied
action and unsupported action. Do not assert exact prose unless it is a product contract.

Run the smallest deterministic suites that prove the slice, then the relevant Odoo suites in a
fresh disposable database. Do not mark unavailable or unrun tests as passing. Do not run a real
write until deterministic action tests pass. For real ACTION, use one disposable record and a
reversible field, require exact preview and unchanged pre-approval state, approve exactly once,
verify exactly one effect, restore/archive the fixture and record only sanitized evidence.

## Documentation and delivery

Update `docs/research/EXECUTION_STATE.md` after evidence changes. If production architecture
changes, add/update the required ADR and current authoritative documents in the same checkpoint.
Preserve historical evidence; add a new dated record rather than rewriting old failures.

Finish with:

1. a concise diagnosis of what changed and why;
2. exact tests actually run and results;
3. remaining validation debt and exact next action;
4. a coherent commit pushed to `origin/main` without force-push.

Continue until the real disposable ACTION passes through preview, one approval, exactly one effect
and verification, or until a genuine external/authority blocker prevents further progress. Stop
and report that blocker instead of weakening an invariant, inventing a router from regexes,
claiming unrun tests passed or broadening the product scope.

---
