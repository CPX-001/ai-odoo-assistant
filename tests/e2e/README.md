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
