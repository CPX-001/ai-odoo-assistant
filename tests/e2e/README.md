# M2 sale.order acceptance harness

This directory contains the two environment-neutral pieces used by M2-08:

- `m2_sale_order_fixture.py` creates an idempotent partner, two non-admin sales
  users, one visible quotation, and one quotation hidden by Odoo's standard
  personal-salesperson record rule. Run it through an Odoo 18 shell.
- `m2_sale_order_browser.mjs` drives the real Odoo web client with Playwright.
  It verifies the positive panel flow, tampers the browser `ScreenContext` with
  the hidden order for the negative flow, and inspects browser network traffic.

All database names, ports, URLs, credentials, order IDs, and output paths are
provided through environment variables. The harness therefore makes no claim
about a deployment layout and does not make `sale` an addon dependency.

The browser script requires a disposable Node environment containing
`playwright` and a Chromium installation. Its required variables are:

```text
M2_ODOO_BASE_URL M2_ASSISTANT_BASE_URL M2_ODOO_DATABASE
M2_E2E_LOGIN M2_E2E_PASSWORD
M2_ALLOWED_ORDER_ID M2_ALLOWED_ORDER_NAME
M2_DENIED_ORDER_ID M2_DENIED_ORDER_NAME
```

`M2_FORBIDDEN_VALUES` may contain comma-separated disposable test secrets. If
set, the browser fails if any of those exact values appears in the observed
Odoo bridge request or response. `M2_E2E_SCREENSHOT` optionally writes a final
screenshot outside the repository.

## M3 source/log Diagnostics acceptance

`tests/integration/test_m3_diagnostics_e2e.py` is the environment-neutral M3
vertical slice. With `ODOO_AI_TEST_DATABASE_URL` pointing to a disposable
PostgreSQL database it runs the authenticated Diagnostics API over a
non-default addon root and file log, verifies exact `action_confirm` lines,
bounded/redacted traceback lookup, readiness, and stale fingerprint recovery.

The real Odoo 18 gate adds both `addons/` and `tests/fixtures/odoo18/` to the
runtime `addons_path`, installs `odoo_ai_assistant,odoo_ai_m3_sale_project` with
their post-install tests, then updates both modules. No database, port, source
root, log file, or service name is encoded in product code.

## M4 real Codex sale.order acceptance

`run_m4_sale_order_codex.py` owns a disposable vertical slice: it creates
separate Odoo/Assistant roles and databases, installs the addon and causal
fixture, starts Odoo and the Assistant Service on free loopback ports, runs a
real authenticated Codex turn through Chromium, checks the business effect and
negative cases, then stops processes and removes its exact roles/databases.

Required variables point only to runtime dependencies; credentials remain in
the external Codex profile and are never supplied to the runner:

```text
M4_ODOO_PYTHON M4_ODOO_BIN M4_ODOO_CORE_ADDONS
M4_CODEX_EXECUTABLE M4_PLAYWRIGHT_ROOT M4_NODE
M4_POSTGRES_ADMIN_DSN
```

Example from the repository root, using placeholders for deployment-specific
paths and a disposable PostgreSQL cluster:

```text
M4_ODOO_PYTHON=/path/to/odoo-python \
M4_ODOO_BIN=/path/to/odoo-bin \
M4_ODOO_CORE_ADDONS=/path/to/odoo/addons \
M4_CODEX_EXECUTABLE=/path/to/codex \
M4_PLAYWRIGHT_ROOT=/tmp/playwright-runtime \
M4_NODE=/usr/bin/node \
M4_POSTGRES_ADMIN_DSN=postgresql://gate-admin@127.0.0.1:5432/postgres \
.venv/bin/python tests/e2e/run_m4_sale_order_codex.py
```

The PostgreSQL identity must be allowed to create/drop the runner's randomized
databases and roles. Use only a disposable cluster. The runner never deletes a
pre-existing database or role name.

## M5 real QUERY + HOW_TO acceptance

`run_m5_query_how_to_codex.py` creates its own Odoo/Assistant databases and
roles, installs a test-only model with an owner record rule, ingests a temporary
knowledge document, and demonstrates QUERY/HOW_TO with real Codex and Chromium.
It also checks a second user, write rejection, retired knowledge, missing Codex,
browser isolation, canaries, DB separation and cleanup.

Required runtime variables mirror M4 and remain deployment inputs rather than
product assumptions:

```text
M5_ODOO_PYTHON M5_ODOO_BIN M5_ODOO_CORE_ADDONS
M5_CODEX_EXECUTABLE M5_PLAYWRIGHT_ROOT M5_NODE
M5_POSTGRES_ADMIN_DSN
```

`M5_CODEX_MODEL` is optional; the reproducible gate default is `gpt-5.4`.

## M6 real ACTION acceptance

`run_m6_action_codex.py` owns a disposable ACTION vertical slice. It creates
separate Odoo and Assistant roles/databases, installs and updates the addon plus
the test-only `odoo.ai.m6.action.item` fixture, runs migrations, starts Odoo 18,
the Assistant Service, a real Codex runtime and Chromium, and removes only its
randomized resources afterward.

The browser proves that preview does not write, approval is explicit, the exact
stored patch is verified, reject does not write, another user/company cannot
approve or read the target, extra browser payload is rejected, stale and expiry
fail closed, XSS/instructions remain data, and Chromium never contacts the
Assistant Service. A loopback fault proxy drops exactly one post-commit response
for the ambiguous-result case; deterministic verification resolves it without a
second write. The report includes sanitized correlation IDs, tool names,
versions, states and expected write counts, never credentials or authority
tokens.

Required runtime variables are explicit deployment inputs:

```text
M6_ODOO_PYTHON M6_ODOO_BIN M6_ODOO_CORE_ADDONS
M6_CODEX_EXECUTABLE M6_PLAYWRIGHT_ROOT M6_NODE
M6_POSTGRES_ADMIN_DSN
```

`M6_ODOO_EXTRA_ADDONS` accepts an optional platform-path-separated list when
the Odoo distribution exposes core and standard addons in more than one root.

Example:

```text
M6_ODOO_PYTHON=/path/to/odoo-python \
M6_ODOO_BIN=/path/to/odoo-bin \
M6_ODOO_CORE_ADDONS=/path/to/odoo/addons \
M6_ODOO_EXTRA_ADDONS=/path/to/odoo/standard-addons \
M6_CODEX_EXECUTABLE=/path/to/codex \
M6_PLAYWRIGHT_ROOT=/tmp/playwright-runtime \
M6_NODE=/usr/bin/node \
M6_POSTGRES_ADMIN_DSN=postgresql://gate-admin@127.0.0.1:5432/postgres \
.venv/bin/python tests/e2e/run_m6_action_codex.py
```

The PostgreSQL identity must be limited to a disposable cluster where it may
create/drop randomized roles and databases. `M6_CODEX_MODEL` is optional; the
default is `gpt-5.4`.
