# Phase 9 validation checkpoint — 2026-09-03

Status: **FOCUSED PASS / REAL PROVIDER VALIDATION BLOCKED; P9 NOT ACCEPTED**

TESTED_SHA: `e227da14cc5faae62c0c0fb0b5796d071c70716b`

Pulled base: `2f9f7a0`

## Environment

- Odoo 18 Community on disposable database `odoo_ai_p9_focus_20260903_cdx1`.
- Python `3.12.3`; PostgreSQL `16.15`.
- Codex App Server executable `codex-cli 0.144.2` with the host-configured primary
  `CODEX_HOME=/home/cpx/.codex`.
- Chrome `152.0.7977.65`; Playwright `1.62.1`.
- No GitHub Actions, production database mutation, usage reset or credential material.

## Focused results

| Gate | Result | Actual evidence |
| --- | --- | --- |
| Python compile + focused Ruff | PASS | changed P9 Python surfaces compiled; Ruff clean |
| Focused dependency-light | PASS | 49 tests in 0.48 s |
| Focused Odoo + P7 fixture | PASS | 25 tests; 0 failures/errors |
| Focused HOOT | PASS | 1 test / 1 assertion |
| Browser composer smoke | PASS | attach, remove, reattach, clean visible projection, bounded unsupported-format error, normal send/redirect/stop |
| `git diff --check` | PASS | no whitespace errors |

The Odoo command updated the addon, installed the fixture addon and selected
`TestCanonicalPlanHostLoop`, `TestPhase8RuntimeInventoryEvidence`,
`TestPhase9Knowledge`, `TestPhase9KnowledgeCapability` and `TestPhase7Fixture`.
The final Odoo result was `0 failed, 0 error(s) of 25 tests`.

The dependency-light command was:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_phase9_knowledge_routing.py \
  tests/unit/test_phase8_evidence_contracts.py \
  tests/unit/test_phase8_evidence_runtime.py \
  tests/unit/test_phase8_extension_evidence.py \
  tests/unit/test_phase8_source_log_evidence.py \
  tests/unit/test_phase7_live_extension_context.py \
  tests/unit/test_capability_provider_extensions.py \
  tests/addon/test_addon_boundaries.py
```

The focused HOOT selector was
`transport-only attachment markers never enter the optimistic user projection`.

## Repairs proved by the focused reruns

1. The addon boundary test now accepts only the two fixed, parameterized P9 FTS SQL
   sites in addition to the existing row-locking sites; generic mutation SQL remains
   prohibited.
2. Odoo metadata and fail-closed exception boundaries satisfy the focused Ruff policy.
3. Attachment markers remain in the transport payload but are excluded from the
   optimistic user projection and conversation title.
4. The display-only submit option is preserved through final UX, turn control,
   cleanup and live TaskPlan service wrappers. The browser rerun showed the clean
   visible question with no internal marker.

## Real runner attempt

The real server ran with two HTTP workers and one cron worker. The runner command was:

```bash
sudo -u odoo env CODEX_HOME=/home/cpx/.codex \
  P9_CODEX_EXECUTABLE=/home/cpx/.vscode-server/extensions/openai.chatgpt-26.707.71524-linux-x64/bin/linux-x86_64/codex \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p9_focus_20260903_cdx1 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons,/odoo/custom/addons/odoo-ai-assistant/tests/fixtures/odoo_addons \
  --no-http < tests/e2e/p9_real_knowledge_gate.py
```

The deterministic upload/index assertions completed before the first real model turn,
so `P9-REAL-UPLOAD-INGEST` is PASS. The provider-backed turn then failed closed with
the sanitized failure route `codex_turn_failed / authentication / unauthorized`.
A direct host check confirmed the primary session's access token is expired and its
refresh token has already been consumed (`refresh_token_reused`). No credential value
was printed or recorded.

| Real gate | Result |
| --- | --- |
| P9-REAL-UPLOAD-INGEST | PASS |
| P9-REAL-CHAT-INGEST | BLOCKED / NOT EXECUTED |
| P9-REAL-FTS | BLOCKED / NOT EXECUTED |
| P9-REAL-CITATIONS | BLOCKED / NOT EXECUTED |
| P9-REAL-ACL | BLOCKED / NOT EXECUTED |
| P9-REAL-REINDEX | BLOCKED / NOT EXECUTED |
| P9-REAL-LARGE-DOCUMENT | BLOCKED / NOT EXECUTED |
| P9-REAL-SEMANTIC-GAIN | NOT APPLICABLE — no vector backend |

## Explicitly unexecuted broad suites

The full repository regression, full addon regression, full HOOT/browser regression
and Product Behavior FULL were not executed. They remain periodic validation debt and
were not required by the P9 focused runbook.

## Exit decision

P9 is not accepted and P10 is not eligible. Reauthenticate the normal primary host
Codex session in `/home/cpx/.codex`, then rerun the complete P9 real runner against
this SHA. Only a seven-of-seven real PASS may replace this checkpoint with immutable
P9 acceptance evidence and advance the execution cursor to P10.
