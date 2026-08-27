# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `a05e75006f53b056f31ab96c3864092d89199480`<br>
Latest product/tooling implementation checkpoint: `fee7c4ee8b532e4529ad5dfd6249caab2c877a88`  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Last real Odoo+Codex commit materially tested: `a05e75006f53b056f31ab96c3864092d89199480`<br>
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.3-provider-crash-reproduction
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

Phase 1 provider/runtime architecture work remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 0
currently_stacked_unvalidated_contract_layers: 0
```

No unvalidated look-ahead implementation slice is currently carried.

## Real evidence already processed

The first real Odoo 18 + Codex 0.149.1 run is recorded under
`docs/research/evidence/phase0/2026-08-27/` and remains authoritative for the current blocker.

Observed state:

- `P0-REAL-HELLO`: four completed captures from five submissions, with material provider instability;
- initial `P0-REAL-READ`: FAIL — no capability-backed evidence in the original capture;
- current `P0-REAL-READ`: PASS at `a05e750` — completed capability-backed read with matching browser-history answer;
- `P0-REAL-ACTION`: FAIL — no preview/approval, provider child crashes coincided with Odoo service loss/restart;
- failure-pair matrix: only one current complete original/UI pair;
- `phase0_report.py`: `ready_for_phase1=false`.

## Completed corrective slice — P0.1

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.1-partial-capture-and-retry-attribution.md`

Implemented at `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892` and materially validated at `121108e55ef0ff91adb0377920f73128875536ac`.

Validation status:

```text
pytest: PASS — 7 tests
py_compile: PASS
P0.1-REAL-PARTIAL-CAPTURE: PASS
recovered transient real observation: NOT OBSERVED (deterministic regression PASS)
```

`VD-P0.1-LOCAL` and `VD-P0.1-REAL` are closed.

## Completed corrective slice — P0.2

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.2-read-acceptance-evidence.md`

Implemented at `fee7c4ee8b532e4529ad5dfd6249caab2c877a88`:

- added a sanitized READ acceptance evaluator for `read_partner`, `query_sales`, and `aggregate_sales`;
- a READ now needs final `completed` state plus observed `tool.started` and `tool.completed` evidence to pass the machine gate;
- request/capture errors reject the READ even if tool events were observed;
- the evaluator does not consume answer text, prompts, raw tool/provider data, credentials, or private reasoning;
- product runtime, Odoo authority, capability execution, ACLs and `su=False` behavior are unchanged.

Deterministic validation actually executed against the exact published implementation contents:

```text
python -m pytest -q tests/unit/test_phase0_read_acceptance.py
3 passed in 0.05s

python -m py_compile tests/e2e/phase0_read_acceptance.py
PASS
```

Revalidated after fast-forwarding to `ffa8dfd04449bcd04e95f27519e455f5d314b9ea`:

```text
python -m pytest -q tests/unit/test_phase0_read_acceptance.py
3 passed in 0.02s

python -m py_compile tests/e2e/phase0_read_acceptance.py tests/e2e/phase0_live_capture.py
PASS

python tests/e2e/phase0_read_acceptance.py \
  docs/research/evidence/phase0/2026-08-27/read-partner-01.json
expected rejection: exit 2, accepted=false, missing tool.started + tool.completed
```

A fresh real READ could not be run from this session. The reachable Odoo endpoint exposed database
`odoo_ai_m1_08_9473`, whereas the recorded Phase 0 fixture/evidence environment used
`codex_m7_odoo_test`; the active Odoo process also predates the current checkout. No Phase 0 capture
credentials or message variables were available, the service configuration was not readable by the
current user, and the documented/default `admin`/`admin` probe did not authenticate. No credentials
were guessed beyond that single standard probe and no live evidence was manufactured.

The earlier blocked attempt was resolved by adapting the available disposable Odoo environment,
updating the addon, restarting the service, and creating an isolated internal user/partner fixture.

Real validation at `a05e75006f53b056f31ab96c3864092d89199480`:

```text
P0-REAL-READ: PASS
Odoo: 18.0
Codex CLI: 0.144.2
final state: completed
tool.started + tool.completed: observed (two bounded tool pairs)
machine acceptance: accepted=true, missing_tool_events=[]
browser history answer matches actual fixture name/email: true
browser final: 16120.006 ms
Odoo restarts during validation: 0
```

The sanitized capture and acceptance result are stored beside the P0.2 evidence record. P0.2 is
complete; this does not authorize ACTION until P0.3 bounds the previously observed provider/Odoo
crash path.

## Validation debt

### VD-P0.2-REAL-READ — CLOSED

```text
validation_id: P0-REAL-READ
gate_type: HARD
origin_slice: P0.2-read-failure-diagnosis
commit_materially_tested: a05e75006f53b056f31ab96c3864092d89199480
result: PASS
evidence:
  - read-partner-a05e750.json
  - read-partner-a05e750-acceptance.json
remaining_downstream_blocker: P0.3 provider crash reproduction must complete before ACTION retry
```

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
commit_materially_tested: mixed; last broad live baseline 8641b013e62018d8d47cfb2a44106ff039b84aca
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
  - architecture decisions that depend on successful read/action/failure baseline evidence
reason: READ now passes; ACTION remains frozen by the unbounded provider/Odoo crash path and the failure-pair matrix is incomplete
```

## Current blocker

```text
P0_PROVIDER_CRASH_REPRODUCTION_REQUIRED
```

P0.2 is complete. ACTION remains frozen until P0.3 reproduces or safely bounds the prior Codex child
crash/Odoo service-loss path. Phase 1 remains blocked by the broader Phase 0 gate.

## Exact next action selection

1. Start `P0.3-provider-crash-reproduction` from current `main`.
2. Inspect the current Codex subprocess boundary, service logs and prior signal-5/service-loss evidence.
3. Define a bounded read-only reproduction that cannot perform a business write.
4. Determine whether the child crash can terminate/restart Odoo; preserve sanitized process/service evidence.
5. Add the smallest deterministic regression or diagnostic fixture justified by the result.
6. Do not retry ACTION until the crash path is bounded, and do not begin Phase 1 production work.

## Planned corrective Phase 0 slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**;
- `P0.2-read-failure-diagnosis` — **COMPLETE**;
- `P0.3-provider-crash-reproduction` — **READY**;
- `P0.4-fault-injection-fixtures` — bounded EOF/timeout/invalid-output fixtures;
- repeat READ/ACTION only under the stop rules, then aggregate Phase 0 report.

## Authorized look-ahead

`P1-PREP-CONFORMANCE` remains potentially eligible only if a later run is blocked solely by unavailable real-environment evidence and the protocol's eligibility test is satisfied. It is not the current priority while P0.3 is READY.

No Phase 1 production provider/runtime refactor is authorized.

## Phase transition rule

Phase 0 remains incomplete until the mandatory real matrix, timing/tool decomposition and at least five distinct original/UI failure pairs pass and `phase0_report.py` reports `ready_for_phase1=true` on materially tested evidence.

## Automation / publication policy

- Do not use GitHub Actions; no runners/workers are available for this roadmap.
- Tests only count when actually executed.
- A remote/GitHub-only run records validation debt rather than assuming success.
- Roadmap checkpoints must be published to `origin/main` when possible so later runs can consume them.
- Never force-push or publish credentials/unsanitized real-environment evidence.

## Resume instructions

Every new run must re-read current `main`, this file, the P0.2 evidence record, current code/tests and the continuous execution protocol before selecting work. Start P0.3; do not retry ACTION or begin Phase 1 until the provider/Odoo crash path is bounded.
