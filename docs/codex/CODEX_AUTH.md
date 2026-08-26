# Codex authentication and account lifecycle

Current embedded-runtime account design. See ADR-018 for the database-scoped activation decision.

## Ownership model

Codex owns the credential format and lifecycle. Odoo does not parse, synthesize or persist provider access/refresh tokens.

The addon derives a private provider home from Odoo's `data_dir`:

```text
<data_dir>/odoo_ai_assistant/codex
```

That directory is passed as `CODEX_HOME` and is managed under the Odoo operating-system identity with restrictive permissions.

## Installation scope vs database scope

The provider credential store is installation/host scoped. Each Odoo database has a separate non-secret activation flag:

```text
odoo_ai_assistant.codex_connection_enabled
```

A database must be enabled and the provider account must report authenticated before chat/runtime access is considered connected.

Fresh installs explicitly start disabled. For compatibility, a missing flag on a database that predates ADR-018 is interpreted as enabled so an upgrade does not silently disconnect an existing installation.

## Executable discovery

The runtime detects the Codex executable from the host or uses the optional non-secret override:

```text
odoo_ai_assistant.codex_executable
```

If the executable or runtime storage is unavailable, the UI/API reports a sanitized unavailable/authentication state rather than token details.

## Official App Server account operations

The account manager delegates lifecycle to Codex App Server, including:

- account status/read;
- device-code login start;
- login cancellation;
- logout;
- rate-limit/status retrieval for administrators.

Odoo stores only sanitized account metadata needed for UI responses. Token material never belongs in PostgreSQL, prompts, turn events or logs.

## UI behavior

- Chat/history are gated until the runtime is authenticated.
- Only system administrators can connect/cancel/logout/manage the account.
- Device-code login exposes the provider verification URL and user code needed by the administrator.
- The Assistant automatically polls while it is open and the browser page is visible.
- Pending login is checked on a short interval (currently 5 seconds); an authenticated account is refreshed less frequently (currently 60 seconds).
- Closing the Assistant or hiding the page stops the account poll; reopening/resuming restarts it.
- There is no requirement for a manual “check authentication” button.

## Logout

Database logout calls the provider logout lifecycle and disables that database's connection flag. Do not implement logout by deleting or editing provider credential files directly.

## Security rules

- Never copy `auth.json` or equivalent provider files into Odoo DB fields/parameters.
- Never log raw App Server auth responses if they may contain secrets.
- Never share credential material with the browser.
- Never fabricate refresh/access tokens or depend on their internal schema.
- Keep account configuration system-admin only.
- Treat backups of `data_dir` as potentially secret-bearing infrastructure backups.

## Tests

Current acceptance should cover fresh database disabled state, legacy-upgrade compatibility, connect/device-code flow state transitions, cancel/logout, unavailable executable/storage, non-admin denial, chat/history gating and UI poll lifecycle.