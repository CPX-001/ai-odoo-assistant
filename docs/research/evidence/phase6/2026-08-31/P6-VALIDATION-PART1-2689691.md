# Phase 6 validation — Part 1

Date: 2026-08-31  
Scope: P6.1, P6.2, P6.3 and P6.5 only

## Lineage and environment

```text
BASE_SHA: f0c3992699ef72aec7b3da176db320ae89a946c2
TESTED_SHA: 268969184c7fbeff479d3f22308576c526ba2692
FINAL_SHA: 268969184c7fbeff479d3f22308576c526ba2692 (product/test candidate)
Odoo: 18.0 Community
Provider: Codex App Server / codex-cli 0.144.2, authenticated ChatGPT session
Browser: Playwright 1.57.0 / bundled Chromium revision 1208
Database: disposable odoo_ai_p6_part1_20260831
```

The evidence/state publication commit after `FINAL_SHA` changes documentation only. Resolve that
published checkpoint with `git log -1 -- docs/research/evidence/phase6/2026-08-31/P6-VALIDATION-PART1-2689691.md`.

The mandatory start sequence was executed before using the checkout:

```powershell
git checkout main
git pull --ff-only
git status --short
git rev-parse HEAD
```

It produced a clean checkout at `BASE_SHA`. No old checkout or prompt-supplied SHA was used as
implementation authority.

The local Odoo service account initially could not traverse the provider-owned Codex home. The
host `acl` package and a narrow read/write/traverse ACL for the `odoo` account on `/home/cpx/.codex`
were applied so the configured real provider path could authenticate in place. Credentials were
not copied, printed or persisted in PostgreSQL. The executable override existed only in the
disposable database; that database and its exact filestore were removed after validation.

## Result matrix

| Gate | Result | Evidence |
|---|---|---|
| P6.1 TaskPlan vs EffectPlan | PASS | Neutral decision/static contracts, focused Odoo validation, focused HOOT projections, and real multistep/replan authority assertions |
| P6.2 adaptive/direct, deliberate and replan | PASS | Focused contracts plus real initial-plan/evidence/replan/progress sequence |
| P6.3 bounded multi-step EffectPlan | PASS | Focused host tests and real ordered two-effect execution; real five-step ceiling |
| P6.5 separate agent budgets | PASS | Focused host budget tests and real reasoning/effect ceilings with bounded termination |
| P6-REAL-MULTISTEP | PASS | 2 typed effects, ordered dependency, full preparation/approval/revalidation/execution/verification, no duplicate |
| P6-REAL-REPLAN | PASS | revision 1 initial -> host read evidence -> revision 2 replan; public summary; no structural progress mutation |
| P6-REAL-LOOP-BOUNDS | PASS | real 8-call reasoning ceiling, real 5-effect ceiling, real provider-decision exhaustion during the first replan reproduction, and focused Odoo counter non-evasion assertions |

Phase 6 is **not COMPLETE**. P6.4/P6.6 and their Phase-2 real gates were not validated here.

## Commands and focused totals

Dependency-light/current P6 contracts:

```bash
python3 -m unittest -v tests.e2e.test_next_decision_contract tests.e2e.test_canonical_plan_proposal tests.e2e.test_phase6_planning_contract tests.e2e.test_phase6_adaptive_planning_contract tests.e2e.test_phase6_direct_mode_short_chain_contract tests.e2e.test_host_loop_contract tests.e2e.test_e2e_decision_sequences
```

Final result: **43 tests, PASS**.

Static checks:

```powershell
git diff --check
```

```bash
python3 -m py_compile addons/odoo_ai_assistant/runtime/agent/planning.py addons/odoo_ai_assistant/runtime/agent/codex_decision.py addons/odoo_ai_assistant/runtime/agent/service.py addons/odoo_ai_assistant/runtime/agent/types.py addons/odoo_ai_assistant/runtime/budget.py
```

Final result: **PASS**.

Focused Odoo invocation used the disposable database, addon update and only these discovered classes:

```text
TestAssistantPlanningPreferences
TestAssistantTurnSettingsSnapshot
TestCodexDecisionAdapter
TestNextDecisionValidation
TestCanonicalPlanHostLoop
TestHostLoopAgentRuntime
TestCapabilityActionPolicyRevalidation
```

The final exact invocation was:

```powershell
wsl.exe -d Ubuntu-24.04 -u root -- sudo -u odoo /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin --config=/etc/odoo-server.conf --database=odoo_ai_p6_part1_20260831 --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons --update=odoo_ai_assistant --test-enable --test-tags=/odoo_ai_assistant:TestAssistantPlanningPreferences,/odoo_ai_assistant:TestAssistantTurnSettingsSnapshot,/odoo_ai_assistant:TestCodexDecisionAdapter,/odoo_ai_assistant:TestNextDecisionValidation,/odoo_ai_assistant:TestCanonicalPlanHostLoop,/odoo_ai_assistant:TestHostLoopAgentRuntime,/odoo_ai_assistant:TestCapabilityActionPolicyRevalidation --stop-after-init --http-port=18092 --gevent-port=18093 --logfile=/tmp/p6-part1-final-odoo.log
```

Final result: **30 selected test methods, 44 Odoo-counted tests, 0 failures, 0 errors**.
Two existing focused modules were initially undiscoverable because they were absent from the addon
test-package imports; after repair, the missing subset ran as 5 methods / 9 Odoo-counted tests and
the complete focused selection above was rerun.

Focused HOOT tests were launched against disposable Odoo at `http://127.0.0.1:18091` with the
bundled Playwright runtime and exact test-name filters. Final focused result: **8 tests, 27
assertions, PASS**:

```text
planning mode response exposes direct and explicit plan only
composer Plan action toggles between direct and deliberate
live TaskPlan accepts bounded public replan metadata
live TaskPlan rejects authority fields and unexplained replans
terminal response accepts current TaskPlan revision contract
stale live TaskPlan cannot replace a newer final revision
equal revision final wins and legacy TaskPlan remains readable
TaskPlan response carries bounded progress without execution authority
```

One initial `filter=TaskPlan` URL unexpectedly expanded to the complete addon HOOT selection
(239 tests / 646 assertions, PASS). That execution was accidental, is recorded for honesty, and is
not used to claim the prohibited complete regression. Two subsequent malformed canonical-name
filter attempts were abandoned after they selected unrelated tests; neither is counted as a gate.

The complete dependency-light, complete Odoo addon, complete historical P0-P5 and complete
repository regressions were **not executed**.

## Real gate evidence

All real scenarios used persisted Odoo turns, the configured provider subprocess, disposable
business records and effective-user execution with `su=False`.

### P6-REAL-MULTISTEP — PASS

```json
{"effect_steps":2,"ordered_dependencies":true,"preview_policy_approval_revalidation":true,"effective_user_su_false":true,"verified_steps":2,"duplicate_effects":0,"provider_execution_authority":false}
```

One user request caused two distinct `odoo.record.patch` proposals. The host persisted positions
0/1 and the second-step dependency, generated previews/preconditions/bindings, required approval,
revalidated, executed exactly once per step and stored two verification results plus one verified
effect receipt. There were no pre-approval business writes. Browser projection intentionally did
not expose internal dependency authority.

### P6-REAL-REPLAN — PASS

```json
{"initial_revision":1,"replan_revision":2,"host_evidence_before_replan":true,"revision_kind":"replan","public_summary":true,"progress_structure_preserved":true,"taskplan_non_executable":true,"private_reasoning_exposed":false,"consecutive_noop_progress":0,"terminal_state":"completed"}
```

The deliberate turn created revision 1, obtained real Odoo schema/query evidence that invalidated
the assumed structure, then submitted revision 2 as `replan` with a short public summary. Normal
progress preserved goal, step IDs and labels. No capability arguments, effect authority or private
reasoning entered the public TaskPlan.

The first reproducible attempt exhausted the 12-decision provider budget because rejected no-op
progress updates could be repeated. That failure was preserved and diagnosed before repair. The
repaired sequence was bounded: initial, rejected no-op, schema, rejected no-op, query, replan,
progress, rejected no-op, final.

### P6-REAL-LOOP-BOUNDS — PASS

Real configured-provider observations:

```json
{"subcase":"reasoning_capability_ceiling","executed_calls":8,"remaining_calls":0,"useful_partial_final":true,"write_barrier":false,"clean_bounded_termination":true}
{"subcase":"effect_step_ceiling","accepted_effect_steps":5,"omitted_step":6,"transparent_limit_answer":true,"write_barrier":false,"business_writes":0,"clean_bounded_termination":true}
```

The model respected both host-projected ceilings and terminated truthfully rather than claiming
unperformed work. The first real replan reproduction also exercised the provider-decision ceiling
and terminated with `agent_provider_decision_budget_exceeded`, rather than looping without bound.

Focused Odoo host-loop regressions then proved that:

- valid TaskPlan revisions do not reset the provider-decision counter;
- rejected TaskPlan retries do not reset or evade correctable/consecutive failure counters;
- after `agent_task_plan_progress_required`, a plan retry is temporarily unavailable until a
  non-plan decision advances the turn;
- exhausted budgets terminate with the corresponding host error.

## Repairs

- Temporarily remove the TaskPlan branch after rejected cosmetic/no-op progress, forcing actual
  turn advancement and preserving bounded convergence.
- Document the neutral adapter behavior for that host state.
- Add dependency-light and Odoo regressions for retry suppression and monotonic decision/failure
  budgets.
- Import the existing host-loop and NextDecision validation modules from the addon test package so
  focused Odoo selection actually discovers them.

Changed product/test files are exactly those in commit `268969184c7fbeff479d3f22308576c526ba2692`.

## Explicitly not executed — Phase 2

```text
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-EFFECT-JOURNAL
```

No P6.4/P6.6 gate and no Phase-7 work was started.
