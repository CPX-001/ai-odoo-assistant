# E2E real-environment result — `9f832af`

Date: 2026-08-27  
Implementation/test SHA: `9f832af4d6b1e6b74659bcd30aab21db481fd4b9`  
Validation ID: `E2E-REAL-ENV`  
Gate: `HARD`  
Result: **PASS**

## Correction under test

Reasoning checkpoints and the ACTION pre-effect barrier now commit on the primary worker cursor.
They no longer open a competing registry cursor that updates the same `odoo_ai_turn` row while the
worker transaction is still active. The ACTION barrier commit also includes the pending private
working transcript and preview activity before the first effect.

The correction preserves Odoo authority, effective-user capability execution with `su=False`, the
private transcript, `CapabilityDefinition`, approval, revalidation, the durable write barrier,
verification and recovery behavior. No business write is committed by a reasoning checkpoint.

An Odoo regression creates a real running turn in a registry cursor, appends pending activity,
commits a working checkpoint on that same cursor, then appends and commits the terminal activity.
A fresh cursor verifies completion and monotonic event ordering. This covers the PostgreSQL row
collision that the prior exact-SHA run exposed.

## Environment and deterministic validation

```text
Odoo: 18.0 Community
Codex CLI / App Server: 0.149.1
database: fresh disposable database
Assistant user: dedicated internal user, su=false product path
authoritative ACTION profile: strict / always confirm

git diff --check: PASS
Python compilation: PASS
standalone convergence: 12/12 PASS
decision sequences: 4/4 PASS
NextDecision contract: 4/4 PASS
working transcript contract: 4/4 PASS
canonical plan contract: 5/5 PASS

addon fresh install: PASS
targeted turn-checkpoint Odoo regression: PASS
combined Odoo queue/runtime/convergence/PLAN/adapter/capability/action suite:
  38 tests, 0 failed, 0 errors
```

The live validation ran from the exact implementation tree committed as the SHA above. Full logs
remain outside Git under `/tmp`; only this sanitized result is published.

## Real HELLO

HELLO completed on the first worker claim with no requeue, diagnostic, approval, barrier or
recovery state.

```text
capture_kind: live_http
expectation_met: true
final_state: completed
event sequence: queued -> started -> reasoning.started -> reasoning.completed -> completed
runtime_unavailable diagnostics: 0
write_barrier: false
browser_final_ms: 8290.246
service_stable: true
```

## Real READ

READ completed and returned an answer matching the disposable fixture. The model first requested a
field outside the effective query schema; the host preserved `field_not_in_schema`, requeued the
bounded decision continuation, and the next decision completed normally. This was not a provider,
database or hidden runtime retry: there was no `runtime_unavailable`, serialization failure or
service restart.

```text
capture_kind: live_http
expectation_met: true
final_state: completed
answer_matches_fixture: true
bounded capability calls: 1
bounded correctable diagnostics: field_not_in_schema=1
runtime_unavailable diagnostics: 0
record_changed: false
write_barrier: false
browser_final_ms: 34353.173
service_stable: true
```

## Real ACTION

The first browser inspection showed that the disposable user's persisted autonomy profile was
`balanced`; under that explicit host policy a moderate reversible patch is auto-authorized even if
the prompt asks for confirmation. The fixture was restored and the user-visible autonomy picker was
set to `strict` before starting the authoritative ACTION. This avoids treating prompt prose as an
approval policy and is now called out in the handoff.

The authoritative browser run then crossed every required boundary:

```text
turn_state before approval: awaiting_confirmation
canonical preview: true
preview target/field/before/after exact: true
record_unchanged_before_approval: true
requires_confirmation: true
approval.required events: 1
approval clicks: 1
approval.approved events: 1
execution.barrier events: 1
effects in authoritative run: 1
verified_effect_receipt working items: 1
final turn state: completed
final plan state: completed
final record matches target: true
recovery.required events: 0
runtime/database diagnostics: 0
service_stable: true
```

The count-only persisted trace for the authoritative turn was:

```text
events:
  queued=1, started=2, reasoning.started=1, reasoning.completed=1
  tool.started=3, tool.completed=3
  tool.preview.started=2, tool.preview.completed=2
  approval.required=1, approval.approved=1
  execution.barrier=1
  tool.verify.started=1, tool.verify.completed=1
  completed=1
working items:
  user_input=1, assistant_decision=3
  capability_call=2, capability_result=2
  plan_step_proposed=1, plan_prepared=1
  verified_effect_receipt=1
```

The second `started` event is the explicit post-approval continuation of the same durable turn, not
a failed attempt or blind retry.

## Aggregate Phase 0 gate

After restoring the disposable field, a separate strict preview-only capture reached
`awaiting_confirmation`. It was rejected through the supported plan-decision route; no effect was
executed and the record remained unchanged. The aggregate evaluator then passed:

```text
phase0_report_exit: 0
ready_for_phase1: true
minimum_live_matrix: hello=true, read=true, action=true, failure=true
timing_decomposition: true
simple_latency_attributed: true
five_failure_pairs: true
failure_pair_path_count: 5
```

## Cleanup and conclusion

The disposable database name was checked against its dedicated prefix before removal. The database
was dropped, absence was verified in PostgreSQL, temporary fixture scripts were removed, credential
environment variables were unset, the browser validation tab was closed and Odoo was left active.

```text
fixture_restored_before_preview: true
preview_rejected_without_execution: true
disposable_database_removed: true
database_count_after_drop: 0
temporary_scripts_removed: true
credentials_unset: true
odoo_service_active_after_cleanup: true
```

The turn/event serialization hard gate and the complete HELLO -> READ -> ACTION real-environment
gate are closed at `9f832af4d6b1e6b74659bcd30aab21db481fd4b9`. Phase 0's aggregate evaluator also reports
`ready_for_phase1=true`.
