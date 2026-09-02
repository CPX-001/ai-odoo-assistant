# Phase 9 acceptance — 2026-09-03

Status: **PASS / P9 ACCEPTED / P10 ELIGIBLE**

TESTED_SHA: `77d470febf67ddee46562907718dc47e975922bb`

Base checkpoint: `6dc2798cbb406e460dc420674c3304b2afeab652`

## Environment

- Odoo 18 Community on disposable database `odoo_ai_p9_focus_20260903_cdx1`.
- Python `3.12.3`; PostgreSQL `16.15`.
- Codex App Server executable `codex-cli 0.144.2` with the provider-owned primary
  `CODEX_HOME=/home/cpx/.codex`.
- Independent real-gate server: two HTTP workers and one cron worker.
- Acceptance reruns executed from detached clean worktree
  `/tmp/odoo-ai-p9-77d470f.snmOCA` at the exact tested SHA; an unrelated dirty-main
  change was neither imported nor committed.
- No GitHub Actions, production database mutation, usage reset or credential material.

## Prior focused baseline retained

The focused checkpoint at `e227da1` remains valid for unchanged P9 surfaces:

| Gate | Result |
| --- | --- |
| Python compile + focused Ruff | PASS |
| Focused dependency-light | PASS — 49 tests |
| Focused Odoo + P7 fixture | PASS — 25 tests, 0 failures/errors |
| Focused HOOT | PASS — 1 test / 1 assertion |
| Browser composer smoke | PASS |

That evidence is recorded in
`P9-VALIDATION-BLOCKED-e227da1.md`. The provider-authentication blocker recorded
there is superseded by this acceptance run.

## Resume, failure and repair

The primary ChatGPT login was refreshed through the supported Codex device-login
flow. The refreshed `auth.json` remained in the host-configured primary
`CODEX_HOME`; no credential content was read, copied, logged or committed. Because
the login recreated the file with mode `0600`, the existing service-user ACL was
restored as read-only (`user:odoo:r--`) before starting the real worker.

The first authenticated real turn exposed a lexical retrieval gap. The original
natural-language query produced an all-term `plainto_tsquery`, so a question with
extra conversational words could miss the correct chunk. An initial OR-only repair
was rejected by the focused ACL regression because weak shared tokens could return
irrelevant accessible chunks for a private-source query.

The accepted repair keeps fixed parameterized SQL and the GIN FTS expression index,
but builds a bounded host-normalized OR tsquery from at most 24 safe terms and
requires a bounded multi-term match threshold. One-term exact markers still work;
natural questions can omit words present in neither the document nor its chunk; weak
one/two-token overlap does not become Evidence. The real fixture was also aligned to
the query language because cross-language semantic retrieval is not a claim of the
lexical-first P9 slice.

## Incremental focused validation at tested SHA

Commands:

```bash
cd /tmp/odoo-ai-p9-77d470f.snmOCA

/odoo/custom/addons/odoo-ai-assistant/.venv/bin/python -m ruff check \
  addons/odoo_ai_assistant/models/knowledge.py \
  addons/odoo_ai_assistant/tests/test_phase9_knowledge.py \
  tests/e2e/p9_real_knowledge_gate.py \
  tests/addon/test_addon_boundaries.py

/odoo/custom/addons/odoo-ai-assistant/.venv/bin/python -m pytest -q \
  tests/addon/test_addon_boundaries.py \
  tests/unit/test_phase9_knowledge_routing.py

/odoo/custom/addons/odoo-ai-assistant/.venv/bin/python -m py_compile \
  addons/odoo_ai_assistant/models/knowledge.py \
  addons/odoo_ai_assistant/tests/test_phase9_knowledge.py \
  tests/e2e/p9_real_knowledge_gate.py
```

Results:

| Gate | Result |
| --- | --- |
| Focused Ruff | PASS |
| Python compile | PASS |
| Addon boundary + routing | PASS — 10 tests |
| Focused `TestPhase9Knowledge` | PASS — 4 test methods, 0 failures/errors |
| `git diff --check` | PASS |

The focused Odoo rerun updated `odoo_ai_assistant` and exercised lifecycle, natural
FTS, citations, reindex staleness, ACL isolation, chat binding and capability
discovery. The initial OR-only attempt failed the private-query assertion and is not
counted as PASS; the thresholded repair rerun passed.

## Real Odoo/Codex command

The runner was executed as the `odoo` service user while the independent server
served cron turns:

```bash
cd /tmp/odoo-ai-p9-77d470f.snmOCA

CODEX_HOME=/home/cpx/.codex \
P9_CODEX_EXECUTABLE=/home/cpx/.vscode-server/extensions/openai.chatgpt-26.707.71524-linux-x64/bin/linux-x86_64/codex \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p9_focus_20260903_cdx1 \
  --addons-path=/odoo/odoo-server/addons,/tmp/odoo-ai-p9-77d470f.snmOCA/addons,/tmp/odoo-ai-p9-77d470f.snmOCA/tests/fixtures/odoo_addons \
  --no-http < tests/e2e/p9_real_knowledge_gate.py
```

Sanitized terminal result:

```json
{"effective_user_su_false": true, "event": "p9_real_knowledge_gate_completed", "gates": {"P9-REAL-ACL": "PASS", "P9-REAL-CHAT-INGEST": "PASS", "P9-REAL-CITATIONS": "PASS", "P9-REAL-FTS": "PASS", "P9-REAL-LARGE-DOCUMENT": "PASS", "P9-REAL-REINDEX": "PASS", "P9-REAL-UPLOAD-INGEST": "PASS"}, "semantic_gain_gate": "NOT_APPLICABLE_NO_VECTOR_BACKEND"}
```

| Real gate | Result |
| --- | --- |
| P9-REAL-UPLOAD-INGEST | PASS |
| P9-REAL-CHAT-INGEST | PASS |
| P9-REAL-FTS | PASS |
| P9-REAL-CITATIONS | PASS |
| P9-REAL-ACL | PASS |
| P9-REAL-REINDEX | PASS |
| P9-REAL-LARGE-DOCUMENT | PASS |
| P9-REAL-SEMANTIC-GAIN | NOT APPLICABLE — no vector backend |
| Effective business user | PASS — `su=False` |

## Explicitly unexecuted broad suites

The full repository regression, full addon regression, full HOOT/browser regression
and Product Behavior FULL were not executed. They remain periodic validation debt;
the P9 repair affected only lexical Knowledge retrieval and its direct boundaries,
which received focused Odoo/dependency-light and complete real-gate reruns.

## Exit decision

All seven mandatory P9 real gates pass against the tested code snapshot. P9 is
accepted at `77d470febf67ddee46562907718dc47e975922bb`; P10 is eligible. P10 must begin
with its mandatory privilege-boundary ADR before any host-operation capability is
implemented.
