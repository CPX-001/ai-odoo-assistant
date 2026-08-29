# Deployment and configuration

This document describes the supported embedded deployment after ADR-016 and ADR-020.
Sidecar-era service ports, Assistant DB configuration and machine secrets are not
current requirements.

## Requirements

- Odoo 18 Community on Linux;
- PostgreSQL as required by Odoo;
- this repository's `addons` directory available in `addons_path`;
- a working Codex executable accessible to the Odoo OS user;
- an absolute, writable Odoo `data_dir`;
- one authenticated primary Codex session accessible to the Odoo OS user.

## Installation

1. Add `<repo>/addons` to Odoo `addons_path`.
2. Make the primary Codex home available to the Odoo service as `CODEX_HOME`.
3. Restart/update Odoo as required for addon discovery and environment changes.
4. Update Apps and install or upgrade `Odoo AI Assistant`.
5. Open Settings and verify the primary account reports authenticated.
6. Configure agent autonomy/risk settings.

No standalone Assistant daemon, per-database Codex login or Alembic migration step is
part of the supported product installation.

## Runtime filesystem and primary session

The addon derives its mutable operational paths from Odoo's effective `data_dir`:

```text
<data_dir>/odoo_ai_assistant/
  runtime/
  cache/
  source/
```

Those addon-owned directories are created/tightened to `0700`. Provider authentication
lives in the host-configured `CODEX_HOME`, which may be outside `data_dir`. If the
variable is absent, `<data_dir>/odoo_ai_assistant/codex` is used as a compatible
managed fallback.

For a systemd deployment, configure the service environment with the real absolute
path and restart the service, for example:

```ini
[Service]
Environment="CODEX_HOME=/srv/codex-primary"
```

Do not copy provider-home contents into PostgreSQL, application-level backups, logs,
prompts or the repository. The Odoo OS identity needs read/write/traverse access. The
legacy `odoo_ai_assistant.codex_connection_enabled` parameter is ignored; a valid host
session is consumed automatically by every database in the installation.

## Codex executable

By default the runtime detects Codex from the host environment. If deployment requires
an explicit path, use the non-secret `ir.config_parameter`:

```text
odoo_ai_assistant.codex_executable
```

The executable must be usable by the same OS identity running Odoo.

## Policy settings

The addon stores these administrator-controlled parameters through
`res.config.settings`:

```text
odoo_ai_assistant.agent_confirmation_mode
  always_confirm | risk_based | protected_only

odoo_ai_assistant.agent_max_auto_risk
  low | moderate | high

odoo_ai_assistant.agent_allow_synthetic_data
  boolean
```

Policy values bound automatic execution; they never bypass Odoo permissions or
capability-level constraints.

## Cron/worker operation

Long turns are persisted and processed by Odoo `ir.cron`. Deployment must allow the
configured Odoo instance to run cron workers/jobs normally. There is no separate AI
scheduler service.

For production verification, test queue claim/cancellation/restart behavior with the
actual Odoo worker/cron configuration rather than assuming a single-process development
server.

## Security checklist

- Odoo `data_dir` is absolute and writable only as intended.
- Odoo owns/controls `<data_dir>/odoo_ai_assistant`.
- `CODEX_HOME` is absolute, exists and is accessible only to intended host identities.
- Codex executable is from a trusted deployment source.
- No tokens are copied into `ir.config_parameter`.
- No sidecar port is opened for the Assistant.
- Reverse proxy exposes only the normal Odoo surface required by the deployment.
- Odoo user/company permissions are configured normally; the Assistant does not require
  a shared technical business user.
- Diagnostics/Settings remain system-admin only.

## Legacy deployment files

`installer/`, `service/`, root `migrations/` and `docs/OPERATIONS_M1.md` document the
retired sidecar architecture. Do not follow their PostgreSQL database, service URL,
bind/port, systemd or shared-secret instructions for a current deployment.
