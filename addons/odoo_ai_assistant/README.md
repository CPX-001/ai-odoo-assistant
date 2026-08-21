# Odoo AI Assistant addon - M1 diagnostics

The M1 addon exposes an administrator-only diagnostics form under
`Settings -> AI Assistant`. All HTTP calls originate in the Odoo server; the
browser receives only sanitized status fields.

The server resolves its local Assistant Service configuration in this order:

1. Odoo system parameters `odoo_ai_assistant.service_url` and
   `odoo_ai_assistant.shared_secret_file`;
2. process environment variables `ODOO_AI_SERVICE_URL` and
   `ODOO_AI_SHARED_SECRET_FILE`.

`service_url` must be an HTTP loopback URL. `shared_secret_file` points to the
protected file created by the host bootstrap; the secret content is read only
server-side and is never stored in a field or sent to the browser. Missing
deployment facts remain `Unknown` rather than being inferred from the DEV host.

M1 deliberately does not add chat, browser assets, ScreenContext, delegation,
ORM tools, source/log access, Codex, or writes.
