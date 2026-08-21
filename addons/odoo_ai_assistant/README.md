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

Contextual delegation uses a separate `ODOO_AI_DELEGATION_SECRET_FILE` setting
on the Odoo server process. The file contains the addon-only signing root, has
no default path, and must not be readable by the Assistant Service account.
This separation lets the service transport a short-lived token without being
able to mint authority for another Odoo user.

The current M2 foundation validates `ScreenContext`, derives identity from the
authenticated Odoo environment, and prepares a server-only delegation. It does
not expose browser assets, source/log access, Codex, or writes.

The Assistant Service can call only the internal POST routes
`/odoo_ai/internal/v1/model-metadata` and
`/odoo_ai/internal/v1/read-records`. Both require the M1 machine-auth header and
an addon-signed delegation header. The Odoo process resolves both secret files
from server environment; no endpoint, token, or secret is sent to the browser.
The service-side gateway base URL is supplied separately through
`ODOO_AI_ODOO_BASE_URL`; it is not a browser setting and has no hardcoded host
or port default.
