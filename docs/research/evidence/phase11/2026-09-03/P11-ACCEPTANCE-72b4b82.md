# P11 acceptance — 72b4b82

Date: 2026-09-03  
Status: **PASS / COMPLETE / ACCEPTED / P12 ELIGIBLE**

## Accepted lineage

```text
72b4b826bddffc20f99f5cd72f14ed95111eab5c
```

The tested checkout was clean `main`, synchronized with `origin/main`. The product
repair is `36d52ec07cd48a1402a0730502ff641e10407d07`; `72b4b82` adds the reproducible real
gate runner without changing addon runtime behavior.

## Environment

- Odoo 18.0 Community, Python 3.12.3 and PostgreSQL 16.15 on Ubuntu 24.04/WSL2.
- Focused database: `odoo_ai_p11_gate_20260903_1352`.
- Real database: `odoo_ai_p11_real_20260903_72b4b82`.
- Codex CLI `0.151.0-alpha.7.2` using the provider-owned
  `CODEX_HOME=/home/cpx/.codex`.
- Independent real-gate server with two HTTP workers and one cron worker.
- Real importer: internal user plus contact-create authority; second internal user had
  no contact-create authority. Business execution was `su=False`.
- Autonomy profile: `full_access`; all six real turns required zero manual approvals,
  as allowed by that profile. The same host preview, EffectPlan, policy binding,
  verification and receipt boundaries still executed.

No production database, customer file, credential, raw provider reasoning or
unsanitized staged rows were used or retained as evidence.

## Failures found and repaired

The initial prepared P11 tests did not pass unchanged. Validation found and repaired
four product defects plus two test/harness defects:

1. the stored normalized mapping contains `column`, but the worker and repair path
   accepted only the external `{column_index, field}` shape. Internal revalidation now
   accepts the persisted shape only when `column` exactly matches the bound header;
2. Odoo 18 serializes falsey `fields.Json` values as SQL `NULL`, so successful chunks
   with no messages and rejected chunks with no record ids violated the original
   required-field constraint. Those receipt fields now allow storage `NULL` while the
   public contract continues to project lists;
3. the raw `SKIP LOCKED` selector could observe a buffered pre-flush `queued` value
   immediately after a rejected chunk and reclaim it. The worker now flushes `state`
   before raw SQL, preserving `partial` and preventing rejected-window replay;
4. automated import sorting changed dependency-sensitive Odoo model load order. The
   original order was restored and documented for Ruff;
5. the focused user fixture lacked the Odoo group that grants contact creation; the
   importing fixture now has that authority while the denial fixture intentionally
   does not;
6. assertions on the global cron return value were replaced with assertions on the
   exact session UUID and immutable counters/receipts, avoiding interference from
   unrelated queued sessions while strengthening replay proof.

All product repairs have focused regression coverage.

## Focused static and module gate

The exact P11 model, provider, test, manifest/init and real-runner files were compiled
and checked with the repository Ruff environment. `git diff --check` also passed.

```text
Python py_compile                         PASS
Ruff                                     PASS — All checks passed
git diff --check                         PASS
fresh addon install/model/XML/security   PASS
addon update at tested SHA               PASS
```

The first fresh install caught the model-order regression above; the repaired fresh
install and subsequent update both succeeded.

## Focused Odoo gate

```bash
/odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p11_gate_20260903_1352 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --update=odoo_ai_assistant \
  --test-enable \
  --test-tags=/odoo_ai_assistant:TestPhase11DataImportSession,/odoo_ai_assistant:TestPhase11DataImportCleanupRepair \
  --without-demo=all --stop-after-init
```

Result: **PASS — 8 selected methods, 0 failures, 0 errors**. The final run at the
tested SHA executed 2,206 queries in 4.83 seconds. Earlier failing runs are not counted
as PASS.

## Real Odoo/Codex gate

The checked-in runner is `tests/e2e/p11_real_import_gate.py`. It was invoked through
`odoo-bin shell` while the independent server owned the normal turn/import cron path:

```bash
CODEX_HOME=/home/cpx/.codex \
P11_CODEX_EXECUTABLE=<host-owned-codex-executable> \
P11_TESTED_SHA=72b4b826bddffc20f99f5cd72f14ed95111eab5c \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p11_real_20260903_72b4b82 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --no-http < tests/e2e/p11_real_import_gate.py
```

Sanitized terminal result:

```json
{"approvals":{"cleanup":0,"interrupt":0,"large":0,"partial":0,"repair":0,"small":0},"effective_user_su_false":true,"event":"p11_real_import_gate_completed","gates":{"P11-REAL-CSV-IMPORT":"PASS","P11-REAL-IMPORT-RECEIPT":"PASS","P11-REAL-LARGE-IMPORT":"PASS","P11-REAL-MAPPING-CORRECTION":"PASS","P11-REAL-PARTIAL-INVALID":"PASS","P11-REAL-RESUME-NO-DUPLICATE":"PASS"},"metrics":{"cleanup":{"corrected_rows":1},"interruption":{"actual_chunks":2,"imported_rows":4},"large":{"actual_chunks":6,"chunk_size":200,"imported_rows":1200,"planned_chunks":6,"total_seconds":67.359,"turn_seconds":64.529},"repair":{"actual_chunks":3,"corrected_rows":1,"repair_revision":1},"small":{"actual_chunks":2,"imported_rows":2,"turn_seconds":77.13}}}
```

Fingerprints and the random run id were produced and asserted by the runner; they are
omitted from the compact copy above because the immutable test database is disposable.

## Named real gates

| Gate | Result | Observed proof |
| --- | --- | --- |
| `P11-REAL-CSV-IMPORT` | PASS | Real attached-file turn inspected, planned, executed and created two exact contacts once in two chunks. |
| `P11-REAL-LARGE-IMPORT` | PASS | 1,200 staged rows, chunk size 200, six planned/six completed chunks, exact database count; total 67.359 s including 64.529 s provider turn and about 2.83 s chunk completion. |
| `P11-REAL-MAPPING-CORRECTION` | PASS | Ambiguous headers were explicitly mapped to `name`/`email`; `company_id` stayed excluded, hostile widening was denied, one cleaned row counted only after commit. |
| `P11-REAL-PARTIAL-INVALID` | PASS | First chunk committed; the second invalid selection wrote zero rows, retained a sanitized rejected receipt and produced truthful `1 imported / 1 failed / 0 remaining`. |
| `P11-REAL-RESUME-NO-DUPLICATE` | PASS | A real repair turn inspected and corrected only row 2/type, retained the rejected receipt, advanced revision to 1 and ended with three receipts and no duplicate. Crash-equivalent pre-commit rollback separately left zero rows/receipts; fresh worker transactions resumed a committed cursor to four exact rows, then replay was inert. |
| `P11-REAL-IMPORT-RECEIPT` | PASS | Sessions exposed bounded aggregate counters, chunk row windows/counts/ids, receipt fingerprints, cleanup fingerprint and repair revision/fingerprint. |

The interruption fixture disables only the disposable import cron while the turn is
created. It explicitly rolls back a fully executed first chunk to reproduce worker
loss before commit, verifies that both business rows and receipt disappear, then uses
fresh registry/cursor worker claims for the committed/restart/replay cases. This is a
deterministic PostgreSQL crash-boundary test; it does not claim an OS-wide Odoo outage.

## Scope honesty

The full repository, full addon, HOOT/browser and Product Behavior regressions were
not executed. They remain periodic validation debt: the P11 runbook authorized the
focused P11 classes and six real gates, and no final focused failure demonstrated a
wider blast radius.

The accepted slice remains create-only CSV. XLS/XLSX/ODS, relational paths,
external-id update/upsert, arbitrary transformation code and automatic background
completion messages remain explicitly outside this acceptance claim.

## Acceptance

All mandatory P11 focused and real gates pass on the accepted implementation lineage.
P11 is complete and Phase 12 controlled source-code modification is eligible to begin
at its bounded workspace/path and privilege design boundary.
