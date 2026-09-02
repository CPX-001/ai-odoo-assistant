# Phase 7 final acceptance — 2026-09-02

Status: **PASS — P7 COMPLETE / ACCEPTED; P8 ELIGIBLE**

TESTED_SHA: `092ac57fe58a3a36765b115e78b2eca687f5dbbc`

## Environment

- Odoo 18 Community on disposable databases `odoo_ai_p7_acceptance_20260902` and
  `odoo_ai_p7_focus_20260902`.
- Codex App Server executable: `codex-cli 0.144.2`; host-configured primary `CODEX_HOME`.
- Chromium `145.0.7632.6`, headless Playwright collector.
- Business capabilities executed as the effective Odoo user with `su=False`.
- No GitHub Actions, usage reset, old provider session, production mutation or unsanitized evidence.

## Acceptance gates

| Gate | Result | Actual evidence |
| --- | --- | --- |
| Focused repaired contracts | PASS | 15 Odoo-counted checks; 0 failure/error |
| Product Behavior SMOKE | PASS | 15/15; quality min/mean 100 |
| P7-REAL-PROVIDER-DISCOVERY | PASS | 25 core / 27 installed; uninstall restored core catalog |
| P7-REAL-SELF-AWARENESS | PASS | real provider batch |
| P7-REAL-DISABLEMENT | PASS | real provider batch |
| P7-REAL-CONTEXT-PROVIDER | PASS | real provider batch |
| P7-REAL-DISCLOSURE | PASS | 120 capabilities; selected `bulk.tool_119`; equal quality |
| P7-REAL-AUTHORITY | PASS | real provider batch |
| Product Behavior FULL x3 | PASS | 54 scenarios, 162/162 HARD PASS |
| Final periodic regression | PASS | consolidated record `FULL-REGRESSION-092ac57.md` |

The disclosure comparison measured eager `6268.954 ms` and lazy `11901.779 ms` in this run. Quality
was equal, so the framework remains implemented while eager disclosure stays the promoted default.

## Repairs validated during acceptance

1. A second provider `agentMessage` item now disables provisional projection instead of invalidating
   the authoritative completed response.
2. Counts and broad reads explicitly disclose that their scope is the records visible with the
   current user's access; missing named records mention access/permissions.
3. Ambiguous records are distinguished with safe visible business values, never raw database IDs.
4. Independent Stop controls now settle normalized provider cancellation as `cancelled`.
5. Queued Stop and scheduler claim are serialized, and historical event sequence allocation locks
   and refreshes the authoritative turn row, eliminating duplicate event sequences.

The five previously failing Product Behavior roots were each repeated three times before the full
rerun (15/15), then passed again in the complete FULL x3.

## Product Behavior result

```text
scenario_count       54
trial_count          162
HARD PASS            162
HARD failures        0
quality mean         99.75
quality minimum      90
```

Selected distributions:

| Metric | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| submit persistence | 27.285 ms | 37.199 ms | 45.543 ms |
| provider decision | 7500.944 ms | 12646.737 ms | 28833.976 ms |
| capability execution | 6.498 ms | 99.063 ms | 458.807 ms |
| preview | 1.783 ms | 6.915 ms | 8.655 ms |
| verification | 1.755 ms | 15.306 ms | 17.586 ms |
| first answer delta | 14000 ms | 52000 ms | 72000 ms |
| final answer | 15000 ms | 53000 ms | 85000 ms |
| observed streaming lead | 1028.760 ms | 11728.908 ms | 21265.859 ms |

The three capacity-exhaustion trials scored 90 because of observational latency, while every HARD
queue, isolation and authority invariant passed.

## Non-HARD limitation retained honestly

The legacy Phase-6 stress prompt that asks for a hundred-point answer and then steers it reproduced
`codex_event_budget_exceeded` twice. It failed closed before any effect. The required active
correction contract is independently covered by `PB-UX-005`, which passed 3/3 in FULL with the new
instruction superseding the old effect. This stress ceiling is not represented as PASS and does not
weaken the accepted event/authority bounds.

## Exit decision

There are no unresolved HARD failures. Phase 7 is accepted at `092ac57`; Phase 8 may start from the
prepared evidence-core packet without carrying P7 validation debt.
