# E2E real-environment result — `e9420ae`

Date: 2026-08-27<br>
Implementation/test SHA: `e9420ae80cf1d6a030312e5e4e76a911c60c7b18`<br>
Validation ID: `E2E-REAL-ENV`<br>
Gate: `HARD`<br>
Result: **FAIL — TURN/EVENT SERIALIZATION COLLISION**

## Exact checkout and environment

The checkout was on the documentation-only descendant `9f261803691337d7b926b5ff61d637ca3a8c8bde`.
Local and remote `main` matched, the tree was clean, and `git diff` from the implementation SHA
through that descendant was empty for `addons/` and `tests/`.

```text
Odoo: 18.0
Codex CLI / App Server: 0.149.1
database: new disposable database
Assistant user: dedicated internal user, su=false product path
confirmation policy: always_confirm
```

No production/customer database or record was used.

## Deterministic and Odoo validation

```text
standalone convergence: 12/12 PASS
decision sequences: 4/4 PASS
NextDecision contract: 4/4 PASS
working transcript contract: 4/4 PASS
canonical plan contract: 5/5 PASS
Python compilation: PASS

addon fresh install: PASS
addon explicit update: PASS
Odoo convergence TransactionCase: 12/12 PASS
Odoo canonical PLAN TransactionCase: 2/2 PASS
Odoo App Server adapter regression: 3/3 PASS
```

The host has `python3` but no `python` alias. The first alias-only invocation therefore exited 127;
the identical standalone commands were immediately executed with `python3` and all passed.

## Real HELLO

The sanitized capture reached `completed` with `expectation_met=true`, and the real one-decision
adapter returned a final answer. It was not a clean hard-gate PASS: the first attempt failed with a
database serialization error, was recorded as `runtime_unavailable`, and the turn completed only
after one automatic retry.

```text
final_state: completed
attempt_count: 2
runtime_unavailable diagnostics: 1
requeued events: 1
working kinds: user_input=1, final_answer=1
write_barrier: false
service PID stable: true
```

## Real READ

READ failed after all three attempts. The provider adapter was no longer the failing boundary:
three `assistant_decision` and three `capability_call` items were durably observable. The disposable
partner remained unchanged.

```text
final_state: failed
error_code: runtime_unavailable
attempt_count: 3
runtime_unavailable diagnostics: 3
working kinds:
  user_input: 1
  assistant_decision: 3
  capability_call: 3
  capability_error: 2
write_barrier: false
partner_phone_is_original: true
service PID stable: true
```

## First failing boundary

```text
last successful provider boundary:
  CodexDecisionEngine.next_decision -> valid final_answer / capability_call

last successful host boundary on READ:
  assistant_decision and capability_call persisted in the private transcript

first failing product boundary:
  independent event persistence updates odoo_ai_turn.last_event_sequence
  -> active primary turn transaction flush/commit
  -> psycopg2.errors.SerializationFailure: concurrent update
```

The HELLO traceback failed in `_execute_claimed_turn()` at its final `cr.commit()`. READ failed when
the runtime entered the capability savepoint and the cursor flushed its stale `odoo.ai.turn` row.
The event transaction and primary turn transaction both update the same turn record. The generic
cron boundary then correctly sanitized the database exception as `runtime_unavailable`, but retries
cannot make this a reliable product path.

This evidence proves a host/event transaction defect outside the adapter-only correction scope.
No host loop, transcript, capability, event, queue, or ACTION lifecycle code was changed during
this validation.

## ACTION decision and cleanup

ACTION was not started. The handoff defines READ as a hard predecessor and forbids continuing to a
real write after a hard-gate failure.

```text
action: NOT_RUN
preview_observed: false
approval_clicks: 0
write_barrier_crossed: false
record_unchanged: true
recovery_required_observed: false
disposable_database_removed: true
odoo_service_active_after_cleanup: true
credentials_unset: true
```

The disposable database was deliberately dropped and is not recoverable; it contained only test
state. Full logs and sanitized capture JSON remain local under `/tmp` and were not committed. This
record contains no password, token, prompt, answer, capability arguments/results, provider output,
customer data, or unrestricted database rows.

## Consequence

Phase 0 remains blocked. The next bounded implementation must remove the turn/event serialization
collision while preserving Odoo authority, `su=False`, the private transcript, capability contracts,
approval, write barrier, verification, and recovery semantics. It needs an Odoo regression that
reproduces independent event persistence during an active primary turn transaction. A new product
SHA must then rerun this handoff from a fresh disposable database, beginning with HELLO and READ.
