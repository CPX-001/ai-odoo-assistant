# P2-P4 real Odoo/browser/provider acceptance

Date: 2026-08-28
Result: `PASS`
P2/P3 materially tested commit: `ba4ba00f9a913854a21b571cbb4559105347cca2`
P4 materially tested commit: `8a4432dc9852eacc422b8c794b6613c75da702a9`
Final addon regression checkpoint: `60a610a68bc0f2a0e3af2066adb5c36f3d1aae26`

The checkpoints are one linear code lineage. The only runtime/test change between the accepted
P2/P3 checkpoint and the accepted P4 checkpoint bounds the cancellation-gate prompt and is covered
by a deterministic regression. The later merge at the final addon checkpoint contains documentation
only and does not alter the tested runtime.

## Environment

```text
Odoo Server 18.0
PostgreSQL 16.15
Python 3.12.3
Codex CLI 0.150.0-alpha.8
Playwright 1.55.0
Chrome for Testing 140.0.7339.16
disposable database: odoo_ai_phase234_20260828_132958
isolated validation HTTP port: 8070
```

The gates used the installed Odoo 18 environment, a private already-authenticated provider session
and real Chromium against Odoo-authenticated product routes. No browser authentication flow was
opened and no provider token was copied into the repository, database, prompt, log or evidence.
The existing Odoo instance on port 8069 was left in place.

## Phase 2 real browser gates

The five scenarios traversed the real persisted turn/status path and verified the rendered failure
family, effect certainty, remediation and retry-control behavior. The fault fixture was armed only
for the disposable `odoo_ai_*` database.

```text
P2-REAL-AUTH      PASS  failed/authentication/after_change/none/reconnect; retry hidden
P2-REAL-ACL       PASS  failed/odoo_access/after_change/none/request_access; limited user
P2-REAL-TIMEOUT   PASS  failed/provider_connection/safe/none/retry; retry visible
P2-REAL-TOOLFAIL  PASS  failed/capability_execution/unknown/none/review; retry hidden
P2-REAL-RECOVERY  PASS  recovery_required/queue_worker/never/unknown/review; retry hidden
```

The runner's deliberately conservative terminal label remained
`OBSERVED_OK_NOT_AUTOMATIC_PASS`; this evidence review promotes the observations to roadmap `PASS`.
No prohibited fields or unbounded provider text were exposed.

## Phase 3 real public-activity gates

```text
P3-REAL-ACTIVITY-READ    PASS  completed; capability start/completion distinct from answer
P3-REAL-ACTIVITY-ACTION  PASS  completed; preview, approval, execution and verification observed
P3-REAL-LIVE-VISIBILITY  PASS  meaningful event visible before terminal state
P3-REAL-REDACTION        PASS  closed event kinds; prohibited fields absent
```

The disposable action used the supported capability/approval/write-barrier path. It did not bypass
effective-user `su=False`, approval, execution or verification. Public activity contained only the
bounded host projection, not raw prompt, provider output, private reasoning or unrestricted
arguments/results.

## Phase 4 real answer-streaming gates

All four gates were rerun together on `8a4432d` after the cancellation fixture repair.

```text
P4-REAL-FIRST-DELTA    PASS  provisional answer observed before terminal completion
P4-REAL-FINAL-PARITY   PASS  provisional stream reconciled with authoritative final answer
P4-REAL-CANCEL-STREAM  PASS  cancelled after first delta; no stale final answer appeared
P4-REAL-UTF8-FRAGMENT  PASS  accented Spanish, n-tilde and emoji markers remained exact
```

Observed first-delta latency ranged from 11.4 to 19.8 seconds in this local run. Streaming remained
provisional throughout; final `NextDecision`, cancellation and effect authority stayed host-owned.

## Defects exposed and repaired

The validation run found only harness/precondition defects; no product authority invariant was
weakened to make a gate pass.

```text
2b838a8  import the landed P3/P4 Odoo tests; commit the shell-created fixture records
d7977d0  grant the disposable action user the normal contact-management group
ba4ba00  select the supported strict profile so the low-risk action exercises approval
8a4432d  bound the cancellation prompt so it reaches a delta within the event budget
```

One P3 attempt was invalidated when the WSL clock jumped while the environment was suspended; it
exceeded Odoo's wall-clock limit and was not counted. A fresh isolated server without that validation
limit produced the accepted result. Earlier failed action attempts exposed the two fixture
preconditions above and were superseded after repair.

## Deterministic and regression validation

```text
P2/P3 gate manifest                         9 definitions valid
P4 gate manifest                            4 definitions valid
P2/P3/P4 JavaScript syntax checks           PASS
failure browser contract                    14 assertions passed
public activity contract                     5 assertions passed
focused P3 Odoo projection                   3 tests, 0 failed/errors
focused P4 Odoo live projection              3 tests, 0 failed/errors
nine P2/P3 backend gate regressors            1 test each, 0 failed/errors
fixture contract unit suite                   4 passed
answer-stream contract unit suite             5 passed
full odoo_ai_assistant addon battery        106 tests, 0 failed/errors
affected-file Ruff and diff checks           PASS
```

The broader repository Ruff invocation still reports pre-existing violations across the active
addon and retired sidecar-era areas. That existing cleanup was not expanded into this P2-P4
acceptance checkpoint.

## Cleanup and scope

The disposable server, database, filestore, temporary Playwright installation and unsanitized raw
validation logs were removed after this sanitized record was prepared. The normal Odoo endpoint on
port 8069 returned HTTP 200 after cleanup.

This evidence closes Phase 2, Phase 3 and Phase 4 only. It makes Phase 5 `READY`; it does not claim
that P5.1 or any later product contract is implemented.
