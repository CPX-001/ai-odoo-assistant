Odoo AI Assistant
=================

This is the installable Odoo 18 Community addon for the embedded AI Assistant runtime.
The browser talks only to Odoo. Long turns are persisted in ``odoo.ai.turn`` and run
through the native Odoo scheduler; no separate HTTP service or daemon is required.

Runtime and security
--------------------

* Identity, companies, ACLs and record rules come from the authenticated Odoo
  environment.
* Capabilities execute with ``su=False`` and use runtime-discovered schemas.
* Codex runs as an ephemeral subprocess under the Odoo operating-system user.
* Mutable state lives below the effective Odoo ``data_dir`` with restrictive
  permissions.
* Settings and Diagnostics are administrator-only Odoo surfaces and never expose token
  material.

Installation
------------

Add the repository ``addons`` directory to ``addons_path``, update the Apps list,
install **Odoo AI Assistant**, and configure the embedded runtime in
``Settings -> AI Assistant``.
