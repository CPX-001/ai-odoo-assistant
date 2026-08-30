# Repository instructions

## Scope

This repository is `CPX-001/ai-odoo-assistant`. The supported product is the Odoo 18 Community addon in `addons/odoo_ai_assistant` with an embedded agent runtime.

## Source of truth

Before changing architecture or behavior, use this order:

1. current code on `main` and accepted ADRs;
2. current documentation listed in `docs/README.md`;
3. tests that exercise the current embedded runtime;
4. dated reports, task packets, PDFs and external references as historical/design evidence.

The PDFs under `docs/source-of-truth/` are dated research snapshots. They are useful design references but are not authoritative over newer code or ADRs.

## Current invariants

- Odoo is the operational host and persistence authority.
- The browser talks to Odoo only; there is no product-required Assistant HTTP sidecar.
- Long turns are persisted in Odoo and claimed by `ir.cron` workers.
- Business capabilities run with the effective user Environment and `su=False`.
- The model proposes; the host validates capability, schema, policy, approval, execution and verification.
- `CapabilityDefinition` is the atomic executable contract. Extend the existing capability framework instead of creating parallel tool/action registries.
- No arbitrary SQL, Python, shell, sudo or unrestricted Odoo method execution is exposed to the model.
- Codex App Server is an ephemeral subprocess. Its credentials remain provider-owned in the host-configured primary `CODEX_HOME` (with the Odoo `data_dir` location only as a compatible fallback), not in PostgreSQL, prompts or logs.

## Legacy areas

`service/`, `installer/`, root `migrations/` and many `docs/codex/` milestone artifacts belong to the retired sidecar lineage. Keep them only as historical/regression evidence unless an explicit task removes them. Do not extend them as the product runtime. See `docs/README.md` and `docs/HISTORICAL_DOCUMENTATION.md`.

## Git workflow

Work directly on `main` unless the user explicitly asks for a branch or pull request. Keep the working history coherent and do not present partial work as finished.

For roadmap/Codex runs whose result must be consumed by later automated runs, a local commit is not a complete handoff. When repository credentials/network permit it:

1. inspect `git status` and commit only a coherent checkpoint;
2. push the checkpoint to `origin/main` without force-pushing or rewriting history;
3. verify that the remote `main` contains the intended commit before reporting the handoff as published.

If push is unavailable or rejected, do **not** claim the result is available in GitHub. Record the local commit SHA and `PUSH_REQUIRED` (plus the reason) in the execution report/state when possible, and tell the user exactly what remains to publish. Never commit credentials or unsanitized real-environment evidence merely to make a handoff visible.

## Roadmap execution and validation

The active stabilization roadmap under `docs/research/` may be executed over multiple independent AI/Codex runs. When doing so, follow `docs/research/CONTINUOUS_EXECUTION_PROTOCOL.md` and reconstruct the next action from `docs/research/EXECUTION_STATE.md` rather than relying on chat memory.

Tests and exit gates only count when they were actually executed in an environment capable of running them. If a slice requires real Odoo 18 + Codex behavior, use `docs/research/REAL_ENV_VALIDATION_PROTOCOL.md` and leave the slice at `REAL_ENV_VALIDATION_REQUIRED` until that evidence exists.

**Do not use GitHub Actions for this roadmap. There are currently no GitHub runners/workers available for project execution or validation.** Do not add `.github/workflows` to advance phases, schedule continuation or satisfy gates. This restriction does not remove the requirement to test; it means tests must be run in the real/local execution environment that actually provides Odoo/Codex and any required browser/runtime dependencies.

### Test-scope rule

Validation is **incremental by default**. Run the smallest set of tests that proves the changed or currently unvalidated contract, including its direct integration boundaries and any explicitly named HARD gates.

Do **not** run the full dependency-light, addon, HOOT/browser or repository regression suite merely because a pull, implementation slice, focused test run or final handoff occurred. A full regression is authorized only when:

1. the user explicitly requests it; or
2. the current authoritative execution state, active slice record or validation runbook explicitly names that full regression as a required gate.

Wording such as "test as appropriate", "validate the change", "if focused tests pass" or "run relevant tests" does not implicitly authorize a full regression. Expand beyond focused tests only for a concrete failure whose root cause or blast radius requires it, and state that reason. Record unexecuted broad suites honestly; do not spend runtime/tokens rerunning already-green unrelated coverage by default.

## Slice sizing rule

Roadmap slices should be **as large as is coherently feasible**, not artificially minimized. Prefer one slice that completes one product/architecture behavior end-to-end — backend/runtime contract, frontend projection where applicable, tests, documentation and cleanup — when those pieces can be implemented and validated together.

Split work only when a real boundary justifies it, for example:

- a HARD gate must be executed before dependent design can safely continue;
- a separate authority/security contract needs independent review;
- the required execution environment is unavailable for only part of the work;
- rollback/recovery risk makes a smaller checkpoint materially safer;
- the combined scope is too large to understand, validate and hand off reliably in one run.

Do **not** create separate roadmap slices merely because work touches different files, layers, tests or commits. Mechanical commit granularity from a tool/API does not define slice boundaries. Avoid chains of tiny slices that leave the intended product behavior only partially implemented while each local fragment appears finished.

## Change workflow

For meaningful changes:

1. inspect current code, ADRs and relevant tests;
2. identify reusable runtime/capability infrastructure;
3. consult relevant project research/external references when they reduce uncertainty;
4. state invariants and failure modes;
5. implement the largest coherent slice that remains feasible to understand, validate and recover as one checkpoint;
6. remove obsolete current-path code when appropriate;
7. run deterministic tests and add agentic evals when model behavior is involved;
8. update current documentation in the same change.

External projects are references for patterns, not architecture requirements.
