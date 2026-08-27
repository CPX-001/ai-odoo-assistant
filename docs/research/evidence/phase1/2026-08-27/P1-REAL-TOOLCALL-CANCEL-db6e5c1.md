# Phase 1 completion validation — `db6e5c1`

Date: 2026-08-27
Implementation/live-test SHA: `db6e5c12c53e9a99ad3a55f7472eb13f93855a06`
Validation IDs: `P1-REAL-TOOLCALL`, `P1-REAL-CANCEL`
Gate: `HARD`
Result: **PASS**

## Environment

```text
Odoo: 18.0 Community
Codex CLI / App Server: 0.144.2
database: fresh disposable local validation database
Assistant user: dedicated internal non-admin fixture user
execution authority: effective-user product path, su=false
runtime account: installation-scoped account authenticated; database connection explicitly enabled
```

The installed addon was loaded from the exact checkout above. A new disposable database was
created, the addon was installed, explicitly updated and exercised through the normal Odoo HTTP,
persisted-turn, cron-worker and embedded Codex App Server path. No production/customer record was
used.

## Deterministic and Odoo validation

The dependency-light validation executed before the live gates:

```text
provider conformance: 8 passed
full unit suite: 184 passed
dependency-light E2E convergence suite: 29 passed
provider/contract Python compilation: PASS
```

The first full addon battery exposed one stale account-settings test that bypassed the accepted
database-scoped connection gate. The test was corrected to use the supported settings
connect/logout actions and committed as `db6e5c1`; no product runtime behavior changed. The focused
regression passed, followed by the complete addon battery:

```text
fresh addon install: PASS
explicit addon update: PASS
focused database-connection regression: PASS
odoo_ai_assistant test stats: 126 executions
Odoo result: 0 failed, 0 errors of 92 tests
process exit: 0
```

No GitHub Actions were used.

## P1-REAL-TOOLCALL

A dedicated non-admin internal user requested a read of one disposable `res.partner` fixture. The
turn completed through the active host-owned decision loop. Sanitized public boundary evidence was:

```text
final_state: completed
tool.started: odoo.get_effective_schema, odoo.query_records
tool.completed: odoo.get_effective_schema, odoo.query_records
effective_user_su: false
fixture_unchanged: true
provider_specific_direct_orm_path: not present
```

The logical capability names came from the host registry and both executed through
`CapabilityExecutor` under the originating user's Environment. No provider-side direct ORM/tool
registry was used.

Result: **PASS**.

## P1-REAL-CANCEL

A deliberately multi-step but read-only partner analysis was submitted and cancellation was sent
after the turn entered its active state. Sanitized observations were:

```text
cancel_response_state: cancel_requested
final_state: cancelled
cancel_event_observed: true
execution_barrier_observed: false
fixture_unchanged: true
Codex App Server processes remaining after completion: 0
subsequent distinct turn state: completed
Odoo service after validation: active and HTTP-responsive
```

The cancelled turn did not cross the write barrier, the disposable record retained its original
value, no provider subprocess remained, and a later distinct greeting turn completed normally.

Result: **PASS**.

## Data handling and cleanup status

The retained evidence contains no password, token, account file, prompt text, assistant answer,
provider stdout/stderr, raw capability arguments/results, business payload or private reasoning.
Only bounded capability identifiers, terminal states, counts and booleans are recorded.

The disposable database was retained only until the close-out documents were written and was then
removed using the validated `odoo_ai_p1_` prefix. The normal Odoo service was restarted after
cleanup.

## Conclusion

Both final Phase 1 HARD gates pass on `db6e5c1`. Together with the retained
`P1-REAL-VERSION`/`P1-REAL-SOAK-100` evidence and the green deterministic matrix, this clears Phase
1 and permits the first Phase 2 failure-contract slice to become `READY`.
