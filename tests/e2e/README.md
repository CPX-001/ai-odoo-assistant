# E2E tests

The scripts in this directory were created across several product generations. Older
sidecar/delegation scripts are retained mainly as historical/regression evidence. Their old service
URL, machine-secret, Assistant DB or standalone API assumptions are **not** current product
requirements.

## Current embedded-product E2E target

New/current E2E coverage should exercise the Odoo addon as the product boundary:

```text
browser/Odoo RPC
 -> conversation + durable turn
 -> Odoo cron worker
 -> AgentTurnService / effective capabilities
 -> Codex adapter
 -> host policy/approval/execution/verification
 -> persisted result/events
 -> browser UI
```

Important scenarios include:

- fresh database automatically consumes the authenticated host session;
- missing/inaccessible primary host session fails closed without a per-database login;
- normal authenticated chat turn;
- account/provider unavailable;
- effective-user ACL/record-rule/field-access/multi-company behavior;
- schema-first query bounds;
- effect preview/approval/verification;
- stale approval/precondition or ambiguous effect recovery;
- cancellation and Odoo restart/stale-lease recovery;
- sanitized progress/diagnostics with no secrets or chain-of-thought;
- prompt injection/untrusted record/document text when relevant.

## P5.3 -> P5.4 acceptance battery

`p5_3_acceptance_batch.py` is the single local orchestrator for the remaining P5.3 acceptance work
before P5.4 becomes eligible. It preserves the formal gate IDs but runs them in one execution:

```text
P5.3-FULL-ADDON-REGRESSION
P5-REAL-SETTINGS-SNAPSHOT
```

It requires a clean exact SHA, runs the complete addon Odoo test battery with `--stop-after-init`,
then starts an isolated loopback Odoo process with two cron threads and executes
`p5_3_settings_snapshot_browser.mjs`. The browser observation is still
`OBSERVED_OK_NOT_AUTOMATIC_PASS`; the batch ends in `PASS_PENDING_EVIDENCE_REVIEW` so formal roadmap
acceptance remains an explicit evidence-review step.

Required environment:

```text
ODOO_BIN
ODOO_CONF
ODOO_AI_ADDONS_PATH
ODOO_AI_P5_BASE_URL
ODOO_AI_P5_DB
ODOO_AI_P5_LOGIN
ODOO_AI_P5_PASSWORD
```

Example:

```bash
python tests/e2e/p5_3_acceptance_batch.py \
  --summary-out /tmp/p5_3_acceptance.json
```

See `../../docs/research/P5.3_VALIDATION_RUNBOOK.md` for the complete gate contract and failure
handling rules.

## Foundation Stabilization Phase 0 capture

`embedded_phase0_scenarios.json` is the machine-readable Phase 0 scenario catalog.
Its format distinguishes persisted-turn outcomes from failures rejected by the current
pre-enqueue runtime/account gate. In particular, an unauthenticated primary Codex session returns
`codex_not_connected` before a turn exists, and a missing Codex executable returns
`codex_unavailable`.

`phase0_live_capture.py` captures supported `enqueue` scenarios against a real Odoo HTTP endpoint.
It authenticates through an Odoo session and writes a deliberately redacted trace: credentials,
message text, screen context, assistant answers, plan payloads and general event payloads are not
retained. Plain HTTP is accepted only for loopback hosts so credentials are not accidentally sent
to a remote clear-text endpoint.

Required inputs are supplied through environment variables:

```text
ODOO_AI_PHASE0_DB
ODOO_AI_PHASE0_LOGIN
ODOO_AI_PHASE0_PASSWORD
ODOO_AI_PHASE0_MESSAGE
```

`ODOO_AI_PHASE0_SCREEN_JSON` is optional. Without it, the runner builds a valid generic Odoo screen
hint. When supplied, it may override the normal screen fields, but the runner always stamps a fresh
`captured_at` at submission time so a saved fixture cannot expire before the trial runs.

Example:

```bash
python tests/e2e/phase0_live_capture.py \
  --scenario hello \
  --out /tmp/phase0/hello-001.json
```

For a failure capture, `--ui-error-code` (or `ODOO_AI_PHASE0_UI_ERROR_CODE`) may be supplied only
after the final product/browser error code has actually been observed. The runner does not invent
that value from backend state.

`phase0_baseline.py` summarizes one trace while preserving the live-capture provenance and outcome
metadata needed by the aggregate gate. `phase0_report.py` accepts either raw captures or those saved
summaries, computes simple latency distributions and evaluates the four Phase 0 exit-gate
conditions. Timing decomposition closes only when one successful read/action turn contains the
queue, provider, tool and finalization points together. The failure-pair gate counts distinct
scenario paths, not repeated trials of the same failure. The command returns exit status `0` only
when the evidence says Phase 1 may start; incomplete evidence returns `2`.

## Legacy scripts

Existing sidecar-era helper scripts may still be run when validating preserved legacy code or when
a current migration deliberately reuses one of its contracts. Passing them does not prove the
embedded runtime works; failing them after an intentional retirement does not by itself indicate a
current-product regression.

For current test priorities see `../AGENTS.md`, `../../docs/CURRENT_STATE.md` and
`../../docs/research/PHASE0_BASELINE.md`.
