Odoo AI Assistant addon — diagnostics and contextual panel
==========================================================

The addon exposes an administrator-only diagnostics form under
``Settings -> AI Assistant`` and an Odoo-native contextual assistant panel for
authenticated internal users. All Assistant Service calls originate in the
Odoo server; the browser receives only sanitized result fields.

The server resolves its local Assistant Service configuration in this order:

1. Odoo system parameters ``odoo_ai_assistant.service_url`` and
   ``odoo_ai_assistant.shared_secret_file``;
2. process environment variables ``ODOO_AI_SERVICE_URL`` and
   ``ODOO_AI_SHARED_SECRET_FILE``.

``service_url`` must be an HTTP loopback URL. ``shared_secret_file`` points to
the protected file created by the host bootstrap; the secret content is read
only server-side and is never stored in a field or sent to the browser. Missing
deployment facts remain ``Unknown`` rather than being inferred from the DEV
host.

Contextual delegation uses a separate ``ODOO_AI_DELEGATION_SECRET_FILE``
setting on the Odoo server process. The file contains the addon-only signing
root, has no default path, and must not be readable by the Assistant Service
account. This separation lets the service transport a short-lived token
without being able to mint authority for another Odoo user.

The panel captures navigation-only ``ScreenContext`` from the active Odoo
controller. Odoo validates that context, derives identity from the
authenticated environment, creates a short-lived server-only delegation, and
calls ``POST /v1/turns/explain``. The M2 ``POST /v1/turns/context-read`` route
remains available for deterministic regressions. The browser never supplies a
trusted ``uid`` or company and never calls the Assistant Service directly.

The deterministic context-read turn discovers the effective model metadata,
then requests only the available fields from this bounded candidate set:
``display_name``, ``name``, ``state``, and ``company_id``. It rereads exactly
the delegated record through Odoo ORM and returns a sanitized record snapshot;
it remains the deterministic pre-read used before Codex or another
``ReasoningEngine`` handles an M4 explanation.

The M4 response returned to the browser contains only answer text, confidence,
limitations, and reduced record/source citations. Generated markdown is
treated as untrusted text and rendered with Owl escaping, not ``t-raw`` or
``innerHTML``. Source citations expose logical module paths, bounded line
ranges, fingerprints, and provenance; physical roots and raw excerpts stay
server-side.

The Assistant Service can call only the internal POST routes
``/odoo_ai/internal/v1/model-metadata`` and
``/odoo_ai/internal/v1/read-records``. Both require the M1 machine-auth header
and an addon-signed delegation header. The Odoo process resolves both secret
files from server environment; no endpoint, token, or secret is sent to the
browser. The service-side gateway base URL is supplied separately through
``ODOO_AI_ODOO_BASE_URL``; it is not a browser setting and has no hardcoded host
or port default.

M3 extends the administrator-only Diagnostics model with fixed actions for
source status/rescan, the ``sale.order.action_confirm`` source check, and a
bounded log/traceback check. These actions call only the corresponding
machine-authenticated Assistant Service routes from the Odoo server. The form
shows logical module/file/line references, fingerprints, provider state, and
redacted excerpts; it does not accept or display physical source roots, log
paths, journal units, credentials, or arbitrary commands.
