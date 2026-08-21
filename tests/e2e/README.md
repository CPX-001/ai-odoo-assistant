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
