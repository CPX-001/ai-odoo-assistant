# Deployment and configuration

This document describes the supported embedded deployment after ADR-016. Sidecar-era service ports, Assistant DB configuration and machine secrets are not current requirements.

## Requirements

- Odoo 18 Community on Linux;
- PostgreSQL as required by Odoo;
- this repository's `addons` directory available in `addons_path`;
- a working Codex executable accessible to the Odoo operating-system user;
- an absolute, writable Odoo `data_dir`.

## Installation

1. Add `<repo>/addons` to Odoo `addons_path`.
2. Restart/update Odoo as required for addon discovery.
3. Update Apps and install `Odoo AI Assistant`.
4. Open Settings as a system administrator.
5. Connect the Codex account using the device-code flow.
6. Configure agent autonomy/risk settings.

No standalone Assistant daemon or Alembic migration step is part of the supported product installation.

## Runtime filesystem

The addon derives all mutable runtime paths from Odoo's effective `data_dir`:

```text
<data_dir>/odoo_ai_assistant/
  codex/
  runtime/
  cache/
  source/
```

These addon-owned directories are created/tightened to `0700`. `codex/` becomes `CODEX_HOME` for provider account state. Do not copy its contents into PostgreSQL, logs, backups intended for application-level data export, or prompts.

## Codex executable

By default the runtime detects Codex from the host environment. If deployment requires an explicit executable path, the runtime reads the non-secret `ir.config_parameter`:

```text
odoo_ai_assistant.codex_executable
```

The executable must be usable by the same OS identity running Odoo.

## Database-scoped account activation

The installation-scoped Codex credential store can be enabled/disabled per Odoo database with:

```text
odoo_ai_assistant.codex_connection_enabled
```

This is a non-secret flag. Fresh databases are initialized disabled; a missing value on pre-ADR-018 databases preserves the previous connected behavior during upgrade.

Account connect/cancel/logout operations are system-administrator actions.

## Policy settings

The current addon stores these administrator-controlled parameters through `res.config.settings`:

```text
odoo_ai_assistant.agent_confirmation_mode
  always_confirm | risk_based | protected_only

odoo_ai_assistant.agent_max_auto_risk
  low | moderate | high

odoo_ai_assistant.agent_allow_synthetic_data
  boolean
```

Policy values bound automatic execution; they never bypass Odoo permissions or capability-level constraints.

## Cron/worker operation

Long turns are persisted and processed by Odoo `ir.cron`. Deployment must allow the configured Odoo instance to run cron workers/jobs normally. There is no separate AI scheduler service.

For production verification, test queue claim/cancellation/restart behavior with the actual Odoo worker/cron configuration rather than assuming a single-process development server.

## Security checklist

- Odoo `data_dir` is absolute and writable only as intended.
- Odoo runtime user owns/controls `<data_dir>/odoo_ai_assistant`.
- Codex executable is from a trusted deployment source.
- No tokens are copied into `ir.config_parameter`.
- No sidecar port is opened for the Assistant.
- Reverse proxy exposes only the normal Odoo surface required by the deployment.
- Odoo database/user/company permissions are configured normally; the Assistant does not require a shared technical business user.
- Diagnostics/Settings remain system-admin only.

## Legacy deployment files

`installer/`, `service/`, root `migrations/` and `docs/OPERATIONS_M1.md` document the retired sidecar architecture. Do not follow their PostgreSQL database, service URL, bind/port, systemd or shared-secret instructions for a current deployment.