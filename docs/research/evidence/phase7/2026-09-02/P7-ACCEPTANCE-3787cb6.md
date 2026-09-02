# Phase 7 acceptance validation — 2026-09-02

Status: BLOCKED_PROVIDER_CAPACITY; no Phase-7 acceptance or Phase-8 eligibility claimed.

BASE_SHA: `f410bd0dcb17f7fe7b2ac3839b6bd27472c4079c`
TESTED_SHA: `6b0db24` (validation checkpoint; prior implementation candidate `3787cb6`)

## Environment and scope

- `git pull --ff-only` reported already up to date on clean `main`.
- Odoo 18 Community, disposable `odoo_ai_p7_acceptance_20260902` and `odoo_ai_p7_core_20260902` databases.
- Host-configured primary Codex home only; configured executable reports `codex-cli 0.144.2`.
- No old account/session, usage reset, production mutation or GitHub Actions used.
- P7 consolidated runbook: focused/static, fixture, SMOKE, six real gates, FULL x3, then final periodic regression.

## Executed checks

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused dependency-light | PASS | 84 tests; P7, Product Behavior, planning, streaming, workflow and social contracts |
| Isolated live extension test module | PASS | 7 tests, including projection caching and fresh JIT context |
| Scoped Ruff/compile/diff check | PASS | P7 capability/provider boundary and changed test |
| Focused Odoo + installed fixture | PASS | 16 methods, 24 Odoo-counted tests; no failure/error |
| Session lifecycle/Auto unit tests in Odoo | PASS | 6 plain unittest tests explicitly executed |
| Clean core install | PASS | addon installed without fixture dependency |
| Focused HOOT | PASS | 10 tests / 32 assertions; planning 4/15, one-shot submit 2/6, live stream 4/11 |
| P7-REAL-PROVIDER-DISCOVERY | PASS | install/uninstall restores identical core catalog: 25 core vs 27 installed capabilities; no stale Skill/context provider |
| Current SMOKE | BLOCKED | second fresh run reached 5/15; provider returned `provider_usage_limit` at `PB-HOW-002`; 5 completed cases passed, remaining 10 unexecuted |
| Other P7 real gates | NOT EXECUTED | pending current-candidate rerun |
| FULL x3 | NOT EXECUTED | pending prerequisites |
| Final periodic regression | NOT EXECUTED | requires green FULL |

## Preserved diagnostics and corrections

1. Initial standalone test collection failed because the new screen-service import ran the Odoo-only services package
   initializer. The test now isolates that package namespace while loading the real screen service. The local pytest
   virtualenv also lacked `lxml`; installed `lxml 6.1.2`. No production behavior changed.
2. Scoped Ruff found an unsorted bulk-capability import block. Corrected import ordering only. These two changes form
   candidate `3787cb6`.
3. First real SMOKE completed 11 cases: 10 PASS, one `PB-HOW-002/navigation_reference_missing`. The disposable database
   lacked `contacts`; the provider correctly reported no available route. Installed the missing fixture prerequisite;
   the assertion was not weakened.
4. During the next case, an idle browser HTTP request exceeded the auxiliary server's default 120-second limit. Its
   automatic reload then used an interpreter without Odoo dependencies. Stopped the incomplete evaluator, cancelled
   its one remaining test turn through the public owner-bound cancellation method, corrected test limits and `PATH`,
   and restarted SMOKE from the beginning. The interrupted case is not PASS.
5. Initial discovery lifecycle attempt ran before refreshing the clean database's module list for the newly added
   fixture addon path. After `ir.module.module.update_list()`, actual install/uninstall passed with identical pre/post
   core catalogs. No discovery cache invalidation workaround was added.
6. Browser login initially rejected a stale session/CSRF token from another disposable DB; obtaining a fresh login
   form succeeded. HOOT ran against the correct database, with no JavaScript errors. Streaming/one-shot checks used
   the desktop viewport; planning's first check reported a viewport-size warning but all assertions passed.

The deterministic gate was rerun after the checkpoint repairs: 323 unit tests, 14 failure-contract assertions and 12
public-activity assertions PASS. The provider-capacity blocker is external to product behavior; no reset credit was
used. Exact continuation is to rerun the complete SMOKE and then FULL x3 from the beginning after quota returns.
