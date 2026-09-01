# Product Behavior Evals v1 — implementation and real baseline checkpoint

Date: 2026-09-01
BASE_SHA: `e100dbabd7b8fc200d1751b584cc167d5092cfd5`
REBASE_TARGET: `c8756b24b2acfe19b9cc97b10687d026b5f26af5`
REAL_TESTED_SHA: working tree based on BASE_SHA, before concurrent P7 live-integration commits
STATIC_ODOO_HOOT_TESTED_SHA: rebased publication candidate
FINAL_SHA: publication commit containing this evidence
Odoo: 18.0 Community
Provider: Codex App Server / `codex-cli 0.144.2`, current host-configured account only

## Result

| Gate | Result | Evidence |
|---|---|---|
| Harness/catalog/static | PASS | 53 focused pytest tests on rebased candidate; scoped Ruff, compile and `git diff --check` PASS |
| Focused Odoo | PASS | 25 selected methods / 31 Odoo-counted tests on rebased candidate; 0 failures, 0 errors |
| Navigation regression repeat | PASS | 11 selected methods / 13 Odoo-counted tests; 0 failures, 0 errors |
| HOOT addon frontend | PASS | 161 tests / 618 assertions on rebased candidate |
| Real SMOKE (pre-rebase candidate) | PASS | 15/15 scenarios, one trial, minimum/mean quality 100 |
| Initial real FULL diagnostic | FAIL (preserved baseline) | 41/54 passed, 13 failures before repairs; minimum 40, mean 94.44 |
| Repaired focused real scenarios | PASS | 9/9: PB-ACT-003/005/012/013, PB-HOW-003/005, PB-READ-013, PB-UX-007, PB-PREF-001 |
| Current-candidate SMOKE + final FULL x3 | BLOCKED | Current configured provider returned `usageLimitExceeded` at PB-ACT-010 before the rebased real gates could run |
| Product Behavior promotion gate | BLOCKED | A post-repair FULL x3 remains required; no HARD failure is being reclassified as PASS |

The provider blocker was classified from its sanitized failure envelope as
`provider_capacity / usageLimitExceeded`. The old account/session was deliberately not used. No usage-reset credit
was consumed. Phase-7 implementation is present on current `main`, but its acceptance remains pending.

No observed failure was deferred as a later-phase dependency. PB-ACT-013 uses the current bounded P6 batch path;
future P11 large-import resume/chunking is explicitly outside this gate.

## Repairs made

- Added the permanent 54-scenario customer-behavior catalog, deterministic graders, real disposable-Odoo runner,
  three personas, real ACL/record-rule fixtures and sanitized per-boundary timing evidence.
- Made Plan a removable one-shot composer selection and captured it immutably only for the submitted turn.
- Restored useful real long-answer streaming while retaining final host schema validation; added provider,
  capability preview/execute/verify and public-feedback timing.
- Strengthened ambiguity handling so missing material contact choices and duplicate targets clarify before writes.
- Added batch approval preview of the first five rows and made PB-ACT-013 exercise 28 valid plus two incomplete rows
  rather than passing without a list.
- Added actual immutable-settings, queue-isolation and conflict-safe Revert interactions to the eval harness, closing
  previous false-positive PASS results.
- Added compact host-verified record references for completed effects and frontend support for them.
- Repaired navigation for normal internal users, filtered irrelevant results matching only generic configuration
  wording, and added Spanish/Catalan tax aliases without weakening ACL checks.
- Fixed evaluator defects for conversation-scoped duplicate-final detection, localized numeric formats, written
  number `dos/ambos`, and recordsets escaping closed cursors.

## Commands executed

Focused deterministic and static checks:

```text
python3 -m pytest -q tests/product_behavior tests/unit/test_product_behavior_eval_harness.py tests/unit/test_provider_decision_timing.py tests/e2e/test_next_decision_contract.py tests/e2e/test_canonical_plan_proposal.py tests/e2e/test_phase6_planning_contract.py tests/e2e/test_phase6_adaptive_planning_contract.py tests/unit/test_answer_stream_contract.py
.venv/bin/ruff check <changed Python Product Behavior/P6 files>
python3 -m py_compile <changed Python Product Behavior/P6 files>
git diff --check
```

Two intermediate PowerShell-to-WSL quoting mistakes passed an empty changed-file expansion to Ruff, causing Ruff to
scan the repository and report 159 and later 179 pre-existing broad lint findings. They were not treated as gates
or repaired in this checkpoint. The corrected explicit changed-file command above passed.

Focused Odoo commands used the disposable database `odoo_ai_product_behavior_20260831`, addon update and these
selections:

```text
--test-tags=/odoo_ai_assistant:TestAssistantPublicReferences,/odoo_ai_assistant:TestCodexDecisionAdapter,/odoo_ai_assistant:TestAssistantTurnSettingsSnapshot
--test-tags=/odoo_ai_assistant:TestAssistantPublicReferences
```

HOOT used the canonical addon filter through `tests/e2e/phase23_hoot_gate.mjs` against the same disposable database:

```text
ODOO_AI_HOOT_CANONICAL=@odoo_ai_assistant
```

Real scenario command pattern (one scenario per focused rerun) was:

```text
PB_SUITE=full PB_SCENARIO=<scenario-id> PB_TRIALS=1 odoo-bin shell --database=odoo_ai_product_behavior_20260831 --no-http < tests/product_behavior/product_behavior_real_gate.py
```

The initial SMOKE and FULL diagnostic used the same runner with `PB_SUITE=smoke PB_TRIALS=1` and
`PB_SUITE=full PB_TRIALS=1`. Business capabilities ran as the selected ordinary Odoo user with `su=False`.

## Preserved first FULL failures and disposition

The first complete diagnostic found failures in PB-GEN-008, PB-READ-003/005/006/011/013,
PB-HOW-005/007, PB-ACT-003/004/005/010 and PB-UX-008. Repairs above address their diagnosed causes. Direct
post-repair focused passes were obtained where provider quota allowed; host Odoo/HOOT coverage passed for record
references, navigation, settings and frontend projection. PB-ACT-010 was the first scenario hit by provider capacity
after those repairs, so it and the final matrix remain unexecuted post-repair and are not marked PASS.

## Exact continuation

After the current account quota is available again:

1. rerun PB-ACT-010 once as the smallest interrupted reproducer;
2. run current-candidate SMOKE once and FULL with three trials;
3. record actual totals and freeze promotion thresholds only from that evidence;
4. continue the remaining `P7_CONSOLIDATED_VALIDATION_RUNBOOK.md` gates only if there are zero unresolved HARD failures.
