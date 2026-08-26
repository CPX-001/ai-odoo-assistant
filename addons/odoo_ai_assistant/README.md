Odoo AI Assistant
=================

Installable Odoo 18 Community addon containing the current embedded AI Assistant runtime.
The browser talks only to Odoo. Long turns are persisted in ``odoo.ai.turn`` and claimed by
native Odoo cron workers; no separate Assistant HTTP daemon or database is required.

Runtime and security
--------------------

* Identity, companies, ACLs, record rules and field access come from the authenticated Odoo Environment.
* Business capabilities execute with ``su=False`` and runtime-discovered/effective schemas.
* ``CapabilityDefinition`` is the atomic safe contract used by reasoning, planning and execution views.
* Core capability providers currently cover Odoo query, actions, batch operations and narrow runtime facts.
* Codex App Server runs as an ephemeral subprocess under the Odoo OS user.
* Provider-owned mutable state lives under the effective Odoo ``data_dir`` with restrictive permissions.
* Settings and Diagnostics are administrator-only; secrets are not stored in PostgreSQL or exposed to prompts/logs.

Installation
------------

Add the repository ``addons`` directory to ``addons_path``, update Apps, install **Odoo AI Assistant**,
then connect Codex and configure agent policy in Odoo Settings.

See ``docs/README.md`` and ``docs/CURRENT_STATE.md`` at repository root for the authoritative current documentation.