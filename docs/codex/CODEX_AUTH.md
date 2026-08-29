# Codex authentication and account lifecycle

Current embedded-runtime account design. ADR-020 supersedes the database activation
introduced by ADR-018.

## Ownership and scope

Codex owns credential format, authentication, refresh and logout. Odoo does not parse,
synthesize or persist provider access/refresh tokens.

One Odoo installation consumes one primary host Codex session. The service receives
its provider home through an absolute environment variable:

```text
CODEX_HOME=/absolute/path/to/the/primary/codex/home
```

When `CODEX_HOME` is absent, the addon retains the compatible managed fallback:

```text
<data_dir>/odoo_ai_assistant/codex
```

`CODEX_HOME` is process configuration, never an `ir.config_parameter`. The service OS
identity must be able to traverse, read and write it because Codex owns refresh and
account-state updates there.

## Shared provider identity, isolated Odoo authority

All Odoo users and databases served by that installation share the provider identity,
plan and rate limits. They do not share Odoo business authority or conversation state.

Every turn remains bound to its originating Odoo user, allowed companies and captured
context. Capability discovery, ACLs, record rules, field access, policy, approval,
execution and verification are evaluated under that effective Environment with
`su=False`. A shared Codex session cannot broaden those permissions.

There is no database-scoped activation flag. The legacy
`odoo_ai_assistant.codex_connection_enabled` parameter is ignored.

## Executable discovery

The runtime detects the Codex executable from the host or uses the optional non-secret
override:

```text
odoo_ai_assistant.codex_executable
```

The executable and `CODEX_HOME` must both be usable by the Odoo service identity. If
either is unavailable, account status and turn submission fail closed with sanitized
codes.

## Account operations exposed by Odoo

Odoo copies only the bounded provider auth file into an ephemeral Linux HOME, as it
already does for product turns, and calls the official App Server account/status APIs
there with refresh disabled. This allows a primary home on DrvFS while leaving
authentication and rotation in the host Codex lifecycle. Product UI/RPC surfaces are
status-only:

- read/refresh sanitized connection status;
- show optional identity, plan and rate-limit metadata to system administrators;
- gate chat/history until the primary session is authenticated;
- poll while the Assistant is visible and stop polling when it is hidden.

Odoo does not start device login, display a device code, or log out the shared account.
Authenticate or change the primary session with the normal Codex CLI/host lifecycle,
then refresh Odoo status. A host logout affects the whole installation.

## Security rules

- Never copy `auth.json` or equivalent provider files into Odoo DB fields/parameters.
- Never commit credentials or copy them into evidence artifacts.
- Never log raw App Server auth responses if they may contain secrets.
- Never share credential material with the browser, prompts or public turn events.
- Never fabricate tokens or depend on their internal schema.
- Keep account metadata and diagnostics system-admin only.
- Treat backups of a managed fallback provider home as secret-bearing infrastructure
  backups.

## Validation

Acceptance covers host `CODEX_HOME` selection and validation, legacy-flag
non-authority, authenticated/unavailable states, non-admin metadata denial, chat gate,
UI polling, service restart and real provider-backed turns. Real evidence records only
bounded state/results and never credential contents.
