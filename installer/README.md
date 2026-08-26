# Retired sidecar installer

This directory belongs to the former deployment that provisioned a standalone Assistant Service and related systemd/bootstrap resources.

It is retained for history and regression evidence only. The supported product is installed as the Odoo 18 addon in `../addons/odoo_ai_assistant`; no separate Assistant daemon, service port, database or shared machine secret is required by the current architecture.

Do not run these scripts as current installation instructions unless a task explicitly targets the retired lineage.

For current installation/configuration use:

- `../README.md`;
- `../docs/DEPLOYMENT_CONFIG.md`;
- `../docs/CURRENT_STATE.md`;
- ADR-016;
- local `AGENTS.md`.

A future external service would require a new architecture decision; this installer must not become current by accident.
