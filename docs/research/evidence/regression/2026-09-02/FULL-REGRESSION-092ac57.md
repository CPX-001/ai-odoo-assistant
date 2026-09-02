# Full current-product regression — 2026-09-02

FULL_REGRESSION: **PASS**

TESTED_SHA: `092ac57fe58a3a36765b115e78b2eca687f5dbbc`

Environment: Odoo 18 Community; Codex CLI `0.144.2`; Chromium `145.0.7632.6`; disposable
`odoo_ai_*` databases; effective business user `su=False`.

| Stage | Result | Executed total |
| --- | --- | --- |
| PERIODIC-FULL-DETERMINISTIC | PASS | 284 unit + 39 E2E contracts + 26 JS assertions |
| PERIODIC-FULL-ODOO-ADDON | PASS | 319 counted tests / 239 methods; 0 failures/errors |
| PERIODIC-FULL-HOOT | PASS | 176 tests / 663 assertions |
| PERIODIC-FULL-REAL-PRODUCT | PASS | permanent smokes and all current P7 real gates |
| PRODUCT-BEHAVIOR-FULL | PASS | 54 scenarios x3 = 162/162 HARD PASS |

## Stage A

Executed the canonical compileall, full `tests/unit`, six current dependency-light E2E contract
files, and both JavaScript contracts. Final rerun after the last test-contract edit was fully green.

## Stage B

Executed `--update=odoo_ai_assistant --test-enable --test-tags=/odoo_ai_assistant` against a
disposable database. Result: `319 tests`, `239 methods`, `0 failed`, `0 errors`.

## Stage C

The canonical `@odoo_ai_assistant` filter ran through `/web/tests` with an administrator collector:
`176 tests`, `663 assertions`, no page errors. An earlier limited-persona collector timed out while
enumerating ACL-inaccessible test metadata; it is an environment adaptation attempt, not the gate.

## Stage D

| Real product contract | Result |
| --- | --- |
| authenticated chat/read + replay | PASS |
| unavailable capability fail closed | PASS |
| preview/approval/write/verify | PASS (Product Behavior actions, 45 verifications) |
| active Stop | PASS |
| active correction | PASS (`PB-UX-005`, 3/3) |
| replay without duplicate final/activity | PASS |
| contextual reference with fresh revalidation | PASS |
| provisional answer streaming | PASS |
| P7-REAL-PROVIDER-DISCOVERY | PASS |
| P7-REAL-SELF-AWARENESS | PASS |
| P7-REAL-DISABLEMENT | PASS |
| P7-REAL-CONTEXT-PROVIDER | PASS |
| P7-REAL-DISCLOSURE | PASS |
| P7-REAL-AUTHORITY | PASS |

The older hundred-point redirect stress reproduced the bounded `codex_event_budget_exceeded` failure
without an effect. It is retained as a non-HARD limit; the required correction smoke passed 3/3.

## Stage E

Product Behavior FULL executed from the beginning after all five diagnosed roots were repaired:
162 HARD PASS, 0 HARD failures, mean quality `99.75`, minimum `90`. Timing distributions and repair
details are recorded in `../../phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md`.

No unexecuted stage is labeled PASS.
