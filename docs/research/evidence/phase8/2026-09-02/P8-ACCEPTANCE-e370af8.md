# P8 acceptance evidence

Date: 2026-09-02
Base pulled from `origin/main`: `ecdee092731c579453edd2aac97813fc1e5f5200`
Tested implementation: `e370af8acb7df175c0a90c8e17520c8576b4c6ce`
Outcome: `PASS / P8 ACCEPTED / P9 ELIGIBLE`

## Environment

```text
Operating system: Ubuntu 24.04 under WSL
Python: 3.12.3
Odoo: 18.0 Community
Codex CLI: 0.144.2
PostgreSQL/Odoo database: odoo_ai_p8_focus_20260902_cdx1 (disposable)
Focused Odoo ports: 18108/18109
Real-gate Odoo ports: 18120/18121
Real-gate workers: 2
Real-gate cron workers: 1
```

The real provider gate used the host-configured Codex executable at
`/home/cpx/.vscode-server/extensions/openai.chatgpt-26.707.71524-linux-x64/bin/linux-x86_64/codex`.
No credential was copied into PostgreSQL, a prompt, this report or a tracked log.

## Pull and static gate

The run started from a clean checkout and executed:

```text
git pull --ff-only origin main
python -m compileall -q <changed P8 Python files>
python -m ruff check <changed P8 Python files and tests>
git diff --check
```

Final result: `compileall PASS`, `ruff PASS`, `git diff --check PASS`.

## Dependency-light focused gate

The final focused command covered the P8 contract/runtime/extension/profile/surface
tests, the new source/log provider tests and the directly affected P7 boundaries:

```text
python -m pytest -q \
  tests/unit/test_phase8_evidence_contracts.py \
  tests/unit/test_phase8_evidence_runtime.py \
  tests/unit/test_phase8_extension_evidence.py \
  tests/unit/test_phase8_supported_surface.py \
  tests/unit/test_phase8_product_profiles.py \
  tests/unit/test_phase8_source_log_evidence.py \
  tests/unit/test_capability_provider_extensions.py \
  tests/unit/test_phase7_feature_negotiation.py \
  tests/unit/test_phase7_live_extension_context.py \
  tests/unit/test_phase7_extension_composition.py \
  tests/addon/test_addon_boundaries.py
```

Result: `61 passed in 0.43s`.

## Focused Odoo gate

The addon and fixture were installed into a disposable Odoo 18 database and the
focused tagged gate ran with the repository addon paths:

```text
sudo -u odoo env PATH=/odoo/venv/bin:... \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p8_focus_20260902_cdx1 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons,/odoo/custom/addons/odoo-ai-assistant/tests/fixtures/odoo_addons \
  --init=odoo_ai_assistant,odoo_ai_assistant_p7_fixture \
  --test-enable \
  --test-tags=/odoo_ai_assistant:TestPhase8RuntimeInventoryEvidence,/odoo_ai_assistant:TestCanonicalPlanHostLoop,/odoo_ai_assistant_p7_fixture:TestPhase7Fixture \
  --stop-after-init --http-port=18108 --gevent-port=18109 \
  --limit-time-real=1200 --limit-time-cpu=1200 \
  --log-level=test --logfile=/tmp/p8-focused-cdx3.log
```

Result: `20 tests, 0 failures, 0 errors` (10 canonical host-loop, 6 installed-addon
fixture and 4 runtime/source/log Evidence tests).

## Real Odoo/Codex Evidence gates

An independent Odoo server with two workers and one cron worker was started against
the disposable database. The gate runner was executed as the `odoo` service user:

```text
P8_CODEX_EXECUTABLE=<host configured Codex executable> \
P8_LOG_FILE=/tmp/p8-real-server.log \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p8_focus_20260902_cdx1 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons,/odoo/custom/addons/odoo-ai-assistant/tests/fixtures/odoo_addons \
  < tests/e2e/p8_real_evidence_gate.py
```

The runner completed three real turns and emitted:

```json
{"effective_user_su_false": true, "event": "p8_real_evidence_gate_completed", "gates": {"P8-REAL-EVIDENCE-POLICY": "PASS", "P8-REAL-FRESHNESS": "PASS", "P8-REAL-INJECTION-BOUNDARY": "PASS", "P8-REAL-LOG-DIAGNOSIS": "PASS", "P8-REAL-PROVENANCE": "PASS", "P8-REAL-SOURCE-DIAGNOSIS": "PASS"}, "turns": 3}
```

This proves bounded installed-addon source/XML diagnosis, correlated configured-log
diagnosis, host-owned citation metadata, explicit stale fingerprints, no retrieval
for social turns, inert hostile Evidence and effective Odoo environments with
`su=False`.

## Repairs made and rerun

1. Added dependency-light package bootstraps so P8 unit tests do not import the live
   Odoo addon package during collection.
2. Applied focused Ruff fixes and annotated only intentional fail-closed exception
   boundaries.
3. Moved the Odoo P8 runtime test into the addon test package so Odoo can discover it.
4. Updated the addon-boundary test for current authentication and replaced its
   blanket SQL ban with an exact allowlist for three host-owned `SELECT ... FOR
   UPDATE` locks; mutation SQL remains forbidden.
5. Added bounded source/XML and configured-log providers, routing, freshness,
   redaction, logical locators and browser-safe citations.
6. Restricted explicitly named module queries to that installed module and improved
   distinct-term scoring after an initial Odoo run chose a generic source match.
7. Corrected the real runner locale to `en_US` and used an isolated `/tmp` freshness
   fixture writable by the Odoo service user.

Every repaired failing set and its direct boundary was rerun. The results above are
the terminal results.

## Explicitly unexecuted

The full repository regression, full addon suite, HOOT/browser suite and Product
Behavior FULL suite were not executed. The active P8 runbook authorizes focused
incremental validation, and no focused failure demonstrated blast radius requiring
those broad suites. They remain periodic validation debt; none is represented as a
PASS here.

Raw `EvidenceLedger` excerpt restoration across reconnect is not claimed. Final
host-owned citation metadata is persisted in the normal result payload, which is the
P8 acceptance requirement exercised here. Richer replay/navigation must reuse the
Odoo transcript rather than add another persistence path.
