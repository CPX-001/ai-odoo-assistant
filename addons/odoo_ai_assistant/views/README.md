# Odoo views

This folder contains server-rendered XML views for Assistant administration/configuration surfaces.

The conversational panel itself lives under `static/src`; these views are mainly Settings and Diagnostics.

## Current views

| File | Purpose |
|---|---|
| `res_config_settings_views.xml` | Odoo Settings integration |
| `runtime_settings_views.xml` | embedded runtime/Codex configuration and status |
| `chat_settings_views.xml` | chat/assistant policy-related settings |
| `assistant_diagnostics_views.xml` | administrator diagnostics surface |

## UI responsibility

Admin views should expose **safe configuration and explainable health**, not raw secrets/provider internals.

Good examples of admin-visible information:

- runtime available/unavailable;
- primary host Codex session state;
- executable path/config health;
- scheduler/turn health;
- enabled policy/profile choices;
- sanitized diagnostic codes.

Avoid rendering credentials, raw provider auth files, prompts or full capability arguments/results.

## Adding settings

Persist configuration in the appropriate Odoo model and use the view only as presentation. If a setting changes capability availability or authority, the host must read/revalidate that setting when building the effective catalog; hiding a UI field is not enforcement.
