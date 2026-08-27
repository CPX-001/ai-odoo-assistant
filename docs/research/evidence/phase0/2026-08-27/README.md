# Phase 0 live validation diagnosis — 2026-08-27

## Current HEAD tested

`8641b013e62018d8d47cfb2a44106ff039b84aca` on `main` after a clean fast-forward from
`origin/main`. Odoo was explicitly restarted after synchronization; the materially tested
process started at 2026-08-27 00:12:17 CEST.

## Environment

- Odoo 18.0 Community, addon manifest `18.0.10.4.6`.
- Database: `codex_m7_odoo_test`.
- PostgreSQL 16.15.
- Codex CLI/App Server 0.149.1, auto-detected by the Odoo service.
- Embedded runtime under `odoo.service`; browser/HTTP traffic terminated at Odoo.
- Provider storage resolved below Odoo `data_dir`; account was connected through the supported
  device-code flow. No credential/account identifiers are recorded here.
- Fixture: disposable `res.partner` 215. Its phone remained empty throughout the run.

## Validations

| Validation | Result | Evidence / notes |
| --- | --- | --- |
| `P0-REAL-HELLO` | PASS with instability | Four completed captures out of five submitted; one failed after three `codex_turn_failed` attempts. |
| `P0-REAL-READ` | FAIL | HTTP capture reached `completed`, but no tool checkpoints exist and the browser answer stated that the Odoo query failed. No real partner data was returned. |
| `P0-REAL-ACTION` | FAIL | No preview/approval was produced. During reasoning, Codex child processes crashed and Odoo exited/restarted. The recovered turn was explicitly cancelled; `write_barrier=false` and the phone remained empty. |
| provider auth missing | PARTIAL / non-gating | Sanitized backend capture exists, but it predates the required Odoo restart and has no observed UI code. |
| provider process missing | PASS pair | Temporary executable override produced backend `codex_unavailable`; browser showed the matching unavailable/configuration state. Override was restored. |
| disconnect / EOF | NOT RUN | No bounded injection fixture was available. |
| timeout | NOT RUN | No bounded injection fixture was available. |
| invalid provider/capability output | NOT RUN | No bounded injection fixture was available. |
| ACL denial / recovery | NOT RUN | Positive read/action prerequisites were already failing. |

## Latency findings

Completed hello final latencies were 18,171.923 ms, 6,726.211 ms, 8,946.417 ms and
7,927.290 ms. Distribution from `phase0_report.py`: p50 8,436.853 ms, p95 16,788.097 ms,
range 6,726.211–18,171.923 ms. The separate failed hello ended at 15,133.521 ms.

For the three stable completed greetings:

- submit-to-persist/worker claim: 282.691–621.208 ms (server event timestamps are only
  second-resolution in these captures);
- provider initialization inside the successful runtime attempt: 397.520–408.716 ms;
- first provider event: 883.507–999.510 ms;
- first answer delta: 5,371.734–7,673.271 ms;
- browser final: 6,726.211–8,946.417 ms.

The dominant stable contributor is model/provider time after initialization, not process startup.
The 18.17 s outlier includes approximately 9 s before the final successful runtime attempt,
consistent with transient failed attempts/requeue. Failed-attempt diagnostic checkpoints rolled
back, so that interval cannot be decomposed further from persisted evidence.

The read capture took 17,130.115 ms; its first answer delta was 15,625.290 ms after runtime start,
but the answer was a functional failure rather than a successful read.

## Failure pairs

| Scenario | original_error_code | ui_error_code | Result / notes |
| --- | --- | --- | --- |
| `provider_process_missing` | `codex_unavailable` | `codex_unavailable` | Complete, current HEAD, controlled and restored. |
| `provider_auth_missing` | `codex_not_connected` | pending | Backend-only capture from the pre-restart process; not counted by the final report. |
| failed hello/provider turn | `codex_turn_failed` | pending | Browser history retained only the user message and exposed no terminal error. |
| disconnect / EOF | not run | not run | Injection fixture missing. |
| timeout | not run | not run | Injection fixture missing. |
| invalid output | not run | not run | Injection fixture missing. |

## Defects discovered

### P0-D1 — Codex child crash coincides with Odoo service loss

- Severity: high.
- Evidence: during the only action attempt, multiple `codex-code-mode-host` 0.149.1 processes
  terminated with signal 5; Odoo subsequently exited and systemd restarted it once.
- Probable subsystem: provider/process boundary; the causal link to the Odoo exit remains
  unproven. The Odoo exit reported an import failure during process startup/re-entry.
- Reproducibility: one of one action attempts; no second attempt by stop rule.
- Confidence: high that both events occurred, medium that they share one cause.
- Phase: investigate in Phase 0 before provider-lifecycle design work.

### P0-D2 — `read_partner` state success is a functional false positive

- Severity: high for the Phase 0 gate.
- Evidence: capture state `completed`, no tool checkpoints, browser answer explicitly reported an
  Odoo query failure.
- Probable subsystem: model capability selection/input or capability execution, plus insufficient
  scenario acceptance in `phase0_live_capture.py`/`phase0_report.py`.
- Reproducibility: one of one real read attempts.
- Confidence: high.
- Phase: diagnose product failure and tighten Phase 0 outcome validation before closing the gate.

### P0-D3 — failed-attempt timing evidence is rolled back

- Severity: medium-high for observability.
- Evidence: failed/requeued attempts persist only their terminal diagnostic code; all provider
  timing events emitted inside the worker transaction disappear. The successful retry begins about
  9 s after submit, but the lost interval cannot be attributed.
- Probable subsystem: turn transaction/event persistence boundary.
- Reproducibility: failed hello and transient retries preceding a completed hello.
- Confidence: high.
- Phase: Phase 0 tooling/observability fix; do not redesign provider lifecycle yet.

### P0-D4 — successful capture retains a transient failure as `original_error_code`

- Severity: medium.
- Evidence: `hello-02.json` finished `completed` but records `original_error_code=codex_turn_failed`
  from an earlier requeue.
- Probable subsystem: `_latest_diagnostic_code()` in the capture tooling does not distinguish
  recovered transient errors from terminal errors.
- Reproducibility: one completed turn with retries.
- Confidence: high.
- Phase: small Phase 0 tooling correction with deterministic regression coverage.

### P0-D5 — failed conversations lose terminal error presentation in history

- Severity: medium.
- Evidence: reopening the failed hello conversation displayed its user message but no failure/error
  state.
- Probable subsystem: history/panel persistence contract.
- Reproducibility: one real failed turn.
- Confidence: high.
- Phase: record now; correction likely belongs to the later failure-contract/chat UX phases unless
  it blocks collecting required Phase 0 UI pairs.

### P0-D6 — transport error discards live-capture evidence

- Severity: medium for tooling.
- Evidence: after about 115 s of action polling, `odoo_http_unavailable` raised before the runner
  wrote any trace, losing the queued/running snapshots already collected.
- Probable subsystem: `phase0_live_capture.py` exception/finalization path.
- Reproducibility: one of one service-loss action attempts.
- Confidence: high.
- Phase: Phase 0 tooling correction; persist a sanitized partial trace on capture failure.

## Tooling problems

- Neither the Odoo virtualenv nor system Python contains `pytest`; the Phase 0 pytest suite was
  therefore not executed. Both attempts to locate an installed runner failed. The three scripts
  passed `py_compile`.
- `write_preview` has no capture artifact because the runner writes only on normal terminal return.
- The runner supports only `entrypoint=enqueue`; plan decision, cancellation and recovery remain
  manual/browser work.
- Required EOF/timeout/invalid-output injection fixtures are named in the catalog but not provided
  by the live runner.

## Architectural observations

- Stable greeting latency is dominated by provider/model generation after initialization;
  provider initialization is about 0.4 s, so process-start optimization alone cannot explain the
  observed 6.7–8.9 s.
- Retry latency is material and currently opaque because diagnostic events share the rolled-back
  worker transaction.
- A `completed` turn state is not sufficient evidence of capability-backed task success.
- No evidence supports changing the ReasoningEngine, process lifetime or streaming architecture
  yet.

## Phase 0 gate

`phase0_report.py` processed eight captures, seven considered live, and returned
`ready_for_phase1=false` (exit status 2).

- PASS according to report: hello present, read capture present, failure present, provider timing,
  simple latency attributable.
- FAIL according to report: action absent, complete tool/provider/finalization decomposition absent,
  only one complete failure pair instead of five.
- Additional human-reviewed correction: the report's read=true is not a real product PASS.

Phase 1 remains blocked for provider/runtime architecture changes. `P1-PREP-CONFORMANCE` remains
look-ahead eligible because it does not consume the failed contract.

## Recommended next slices

1. `P0.1-partial-capture-and-retry-attribution`: persist sanitized partial traces and distinguish
   terminal errors from recovered requeues.
2. `P0.2-read-failure-diagnosis`: reproduce the partner query with bounded capability diagnostics;
   add outcome assertions that reject a completed apology as READ success.
3. `P0.3-provider-crash-reproduction`: isolate the 0.149.1 code-mode signal-5 crash without a write
   request and determine why Odoo exited.
4. `P0.4-fault-injection-fixtures`: add bounded EOF, timeout and invalid-output fixtures reusable by
   the existing scenario catalog.
5. Repeat READ, then ACTION only after READ passes and the crash cause is bounded.

## Manual tests required

- Re-run the exact READ fixture on partner 215 and verify both tool events and the real name/email
  in the browser answer.
- Re-run ACTION only after P0-D1 is bounded: require preview, explicit approval, one execution,
  verification, and confirm phone before restoring it to empty.
- Complete four additional original/UI pairs by observing the final browser category, not by copying
  backend codes.
- Install/use an approved pytest environment and execute the four Phase 0 unit test modules.

## Handoff

Start from this directory and `report.json`; do not repeat environment discovery, account login,
process-missing injection or the initial latency series. The disposable partner is 215 and its
phone is empty. First inspect P0-D1 and P0-D2. Keep Phase 0 open and do not start the Phase 1
provider refactor.

## Subsequent P0.2 validation

`P0-D2` was closed for the P0.2 slice at
`a05e75006f53b056f31ab96c3864092d89199480` in an adapted disposable local Odoo 18 environment
using Codex CLI 0.144.2. The new `read_partner` capture completed with two bounded tool
start/completion pairs, passed the machine acceptance gate, and its authenticated browser-history
answer matched the actual fixture name/email. See `P0.2-read-acceptance-evidence.md`,
`read-partner-a05e750.json` and `read-partner-a05e750-acceptance.json`.

This does not clear `P0-D1`: P0.3 must still bound the prior provider-child/Odoo service-loss path
before ACTION is retried. The overall Phase 0 gate and failure-pair matrix remain open.

## Subsequent P0.3 validation

`P0-D1` was bounded for the current supported local environment at
`c114f15a1fe82d102df3c129661fca87ceaeb235`. Odoo 18 Community with addon `18.0.10.4.6` and
Codex CLI `0.144.2` completed three `hello` probes plus one capability-backed `read_partner`
probe. The read persisted three `tool.started` events. All four attempts retained stable service
PID/start identity/restart count, remained `active/running`, had journal access and recorded zero
signal-5 or `codex-code-mode-host` failure lines.

See `P0.3-provider-crash-reproduction.md` and the two sanitized
`p0.3-provider-crash-probe*-c114f15.json` artifacts. This closes P0.3, not the aggregate Phase 0
gate: ACTION and at least four additional complete failure pairs remain pending.

## Subsequent P0.4 and failure-matrix validation

P0.4 was materially validated at `90088215f247716b57e5c19c2502cc2d33a78e51` using Odoo 18,
addon `18.0.10.4.6` and headless Chrome `151.0.7922.174`:

- `codex_process_eof -> service_unavailable`;
- `codex_read_timeout -> service_unavailable`;
- `codex_answer_invalid -> service_unavailable`.

Every turn ended `failed`; Chrome observed the final Assistant failure surface; the executable
override was restored after each case; and Odoo remained stable during every measured trial. The
database gate supplied the fifth pair, `codex_not_connected -> codex_not_connected`, without
logging out or altering provider credentials.

The aggregate `report-9008821.json` now has `five_failure_pairs=true`, timing decomposition and
simple latency attribution true. It remains `ready_for_phase1=false` solely because the ACTION
baseline is absent.

## P0-REAL-ACTION rerun at 38c7c9a

The current-main browser rerun failed closed. A dedicated temporary internal user with the strict
policy requested one reversible partner-phone update through the real Assistant panel. The turn
completed after three bounded tool pairs but produced a zero-step completed plan, so the required
approval preview never appeared. No approval was sent, no write barrier was crossed, and the
partner remained unchanged. Odoo retained the same PID before/after; the temporary fixture and user
were archived.

The relevant standalone regression suite passed 33/33. The separate `write_preview` capture and
aggregate report were not run after the authoritative ACTION failed. See
`P0-REAL-ACTION-result-38c7c9a.md`. Phase 0 is blocked on diagnosing the zero-step write outcome;
Phase 1 remains locked.

## Corrected ACTION rerun at 97617fe

The planning-obligation correction at `075138d7` first passed executable local validation after
its Odoo test was registered: 39 standalone tests, 9 planning/action/revalidation tests and 20
embedded-runtime/framework/batch tests all passed.

The subsequent real browser ACTION nevertheless reproduced the original failure: three bounded
tool pairs, terminal `completed`, `plan_step_count=0`, no preview, no approval and no effect. The
disposable record remained unchanged and Odoo retained PID `75689`. The sanitized acceptance
evaluator rejected the evidence with `action_plan_missing`, `approval_preview_missing` and
`approval_not_required`.

See `P0-REAL-ACTION-corrected-result-97617fe.md`. Phase 0 remains blocked; repeating the same ACTION
without a materially new correction is not authorized, and Phase 1 remains locked.

## ACTION v2 run at 5995717

The stage-only PLAN projection and diagnostic correction first passed 30 standalone tests and 44
targeted Odoo planning/action/runtime/capability tests. The primary addon was then upgraded and the
authenticated product path rerun with a disposable partner and strict temporary user.

Codex saw six reasoning and six planning definitions but selected no tool, staged no proposal and
completed with a low-confidence read-only result. All plan counts were zero, no preview appeared,
no approval/barrier/effect/verification occurred, the record remained unchanged and Odoo stayed on
the same active process. Fixtures were archived/restored and the disposable test database was
removed.

The last successful boundary was `planning_catalog_exposed`; the first missing required boundary
was `plan_step_staged(odoo.record.patch)`. See
`P0-REAL-ACTION-v2-result-5995717.md`. The next correction is the bounded host-owned decision loop
defined in `../../../E2E_AGENT_LOOP_CONVERGENCE.md`, not another prompt-only retry.

## E2E convergence, adapter repair and final PASS

The host-owned decision loop and canonical plan path first exposed an App Server 0.149.1 Structured
Outputs incompatibility at `ee723a7`: the root `oneOf` schema was rejected before the first
decision. The adapter-only correction at `e9420ae` preserved the specific
`codex_output_schema_invalid` diagnostic and reached valid real decisions, but exact-tree product
validation then exposed a separate PostgreSQL turn/event serialization collision. HELLO required a
runtime requeue, READ failed after three attempts and ACTION was correctly not attempted. See
`E2E-REAL-ENV-result-e9420ae.md`.

Checkpoint `9f832af4d6b1e6b74659bcd30aab21db481fd4b9` commits reasoning checkpoints and
the ACTION pre-effect barrier on the primary worker cursor and adds a real-cursor Odoo regression.
Standalone suites, fresh installation and 38 selected Odoo tests passed with zero failures/errors.
Real HELLO completed cleanly; real READ completed without runtime/database retry; and the strict
browser ACTION produced an exact preview with the record unchanged, then one approval caused one
barrier/effect and one verified receipt with no recovery.

After restoring the field, a separate preview-only capture was rejected without execution. The
aggregate report exited `0` with the full live matrix, five failure pairs and
`ready_for_phase1=true`. The disposable database was removed and Odoo was left active. See
`E2E-REAL-ENV-result-9f832af.md`. Phase 0 is complete.
